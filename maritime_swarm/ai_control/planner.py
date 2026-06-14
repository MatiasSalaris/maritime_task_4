"""The open-ended agent decider.

One call returns the agent's reasoning, any coordination messages, and a single
action (tool call). The decider is a PURE LLM — no keyword rules and no offline
heuristic: every agent must be driven by its own language model. To stay live
when one provider's budget is exhausted, the decider holds an ordered list of
OpenAI-compatible providers (Groq first, OpenAI as failover) and transparently
fails over on a rate-limit / error.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from maritime_swarm.ai_control.observation import Observation
from maritime_swarm.ai_control.prompts import (
    ACTION_SENTINEL,
    build_decision_system_prompt,
    build_decision_user_prompt,
)
from maritime_swarm.ai_control.scene import Scene
from maritime_swarm.ai_control.tools import ToolContext, ToolRegistry
from maritime_swarm.llm.groq_client import inferenza_stream

logger = logging.getLogger(__name__)

_MSG_TYPES = {"intent", "proposal", "ack", "objection", "handoff", "report", "status"}


class _ReasoningStreamer:
    """Forward only the reasoning prose (before the action sentinel) to a sink.

    The streamed completion is ``<reasoning prose> ###ACTION### <json>``. We want
    the live chain-of-thought panel to show only the prose, so we emit text up to
    the sentinel and stop — holding back a short tail each step so the sentinel is
    never split across deltas and partially shown.
    """

    def __init__(self, sink: Callable[[str], None] | None) -> None:
        self._sink = sink
        self._buf = ""
        self._emitted = 0
        self._done = False

    def feed(self, delta: str) -> None:
        if self._done or self._sink is None:
            return
        self._buf += delta
        hit = self._buf.find(ACTION_SENTINEL)
        if hit != -1:
            self._emit_upto(hit)
            self._done = True
            return
        # hold back the last (len(sentinel)-1) chars in case the sentinel spans deltas
        safe = max(self._emitted, len(self._buf) - (len(ACTION_SENTINEL) - 1))
        self._emit_upto(safe)

    def flush(self) -> None:
        """Emit any held-back tail if the sentinel never arrived (prose-only reply)."""
        if not self._done and self._sink is not None and ACTION_SENTINEL not in self._buf:
            self._emit_upto(len(self._buf))

    def _emit_upto(self, idx: int) -> None:
        if idx > self._emitted and self._sink is not None:
            self._sink(self._buf[self._emitted:idx])
            self._emitted = idx


def _extract_json(blob: str) -> dict[str, Any]:
    """Pull the JSON object out of the post-sentinel tail; {} if none/invalid."""
    blob = blob.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    start, end = blob.find("{"), blob.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        obj = json.loads(blob[start:end + 1])
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        return {}


def split_reason_action(text: str) -> tuple[str, dict[str, Any]]:
    """Split a reason-then-act completion into (reasoning prose, action JSON dict)."""
    if ACTION_SENTINEL in text:
        reasoning, _, rest = text.partition(ACTION_SENTINEL)
    else:  # fallback: reasoning runs up to the first brace, JSON from there
        brace = text.find("{")
        reasoning, rest = (text[:brace], text[brace:]) if brace != -1 else (text, "")
    return reasoning.strip(), _extract_json(rest)


def normalise_decision(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce an LLM response into {reasoning, messages, action}."""
    action = raw.get("action") or {}
    if not isinstance(action, dict):
        action = {}
    tool = action.get("tool") or action.get("name")
    args = action.get("args") or action.get("arguments") or {}
    if not isinstance(args, dict):
        args = {}

    msgs_raw = raw.get("messages") or []
    if isinstance(msgs_raw, dict):
        msgs_raw = [msgs_raw]
    messages = []
    for m in msgs_raw if isinstance(msgs_raw, list) else []:
        if not isinstance(m, dict):
            continue
        text = str(m.get("content") or m.get("text") or "").strip()
        if not text:
            continue
        mtype = str(m.get("type") or "status").lower().strip()
        if mtype not in _MSG_TYPES:
            mtype = "status"
        messages.append({"to": str(m.get("to") or "all"), "type": mtype, "content": text})

    return {
        "reasoning": str(raw.get("reasoning") or "").strip(),
        "messages": messages[:3],
        "tool": tool,
        "args": args,
    }


class AgentDecider(Protocol):
    def decide(
        self, obs: Observation, ctx: ToolContext, scene: Scene, mission: str,
        peers: list[dict[str, Any]], shared_contacts: list[dict[str, Any]],
        messages: list[dict[str, Any]], current_task: str | None, registry: ToolRegistry,
        task_status: str = "idle", silent_peers: list[str] | None = None,
        outbox: list[dict[str, Any]] | None = None, is_leader: bool = False,
        on_token: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        ...


@dataclass
class LLMProvider:
    """One OpenAI-compatible LLM endpoint the decider can call."""

    name: str
    api_key: str
    model: str
    base_url: str
    temperature: float = 0.3
    cooldown_until: float = field(default=0.0)  # monotonic; set after a 429


class RateLimitError(RuntimeError):
    """Raised when every configured provider is rate-limited / unavailable."""


class LLMDecider:
    """Pure-LLM decider with transparent failover across providers.

    Tries each provider in order (Groq first, OpenAI as failover), skipping any
    currently in 429 cooldown. The first provider that streams a completion wins.
    If every provider is rate-limited or errors, raises so the brain backs off —
    there is NO heuristic fallback: an agent never acts without its LLM.
    """

    _PROVIDER_COOLDOWN_S = 30.0

    def __init__(self, providers: list[LLMProvider]) -> None:
        if not providers:
            raise ValueError("LLMDecider needs at least one provider")
        self.providers = providers

    def decide(self, obs, ctx, scene, mission, peers, shared_contacts, messages, current_task, registry,
               task_status="idle", silent_peers=None, outbox=None, is_leader=False, on_token=None):
        user_prompt = build_decision_user_prompt(
            obs, ctx, scene, mission, peers, shared_contacts, messages, current_task,
            task_status, silent_peers, outbox, is_leader)
        system_prompt = build_decision_system_prompt(registry, is_leader)

        now = time.monotonic()
        ready = [p for p in self.providers if p.cooldown_until <= now] or self.providers
        last_exc: Exception | None = None
        for provider in ready:
            streamer = _ReasoningStreamer(on_token)  # fresh per attempt — no double prose
            try:
                raw = inferenza_stream(
                    prompt=user_prompt, api_key=provider.api_key,
                    system_prompt=system_prompt, model=provider.model,
                    temperature=provider.temperature, on_token=streamer.feed,
                    base_url=provider.base_url,
                )
                streamer.flush()
                reasoning, action_obj = split_reason_action(raw)
                if provider is not self.providers[0]:
                    logger.info("[%s] using failover provider '%s' (%s)",
                                ctx.agent_id, provider.name, provider.model)
                return normalise_decision({
                    "reasoning": reasoning,
                    "messages": action_obj.get("messages"),
                    "action": action_obj.get("action"),
                })
            except Exception as exc:  # noqa: BLE001 — try the next provider
                last_exc = exc
                if "429" in str(exc):
                    provider.cooldown_until = time.monotonic() + self._PROVIDER_COOLDOWN_S
                    logger.info("[%s] provider '%s' rate-limited (429) — failing over",
                                ctx.agent_id, provider.name)
                else:
                    logger.warning("[%s] provider '%s' error: %s", ctx.agent_id, provider.name, exc)

        # Everything we tried failed — surface 429 so the brain's cooldown kicks in.
        raise RateLimitError(f"all LLM providers unavailable (429): {last_exc}")
