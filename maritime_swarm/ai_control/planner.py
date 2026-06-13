"""The open-ended agent decider.

One call returns the agent's reasoning, any coordination messages, and a single
action (tool call). The real planner (GroqDecider) is a pure LLM — no keyword
rules. A small HeuristicDecider keeps the loop alive offline / in tests.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from maritime_swarm.ai_control.geo import haversine_km
from maritime_swarm.ai_control.observation import Observation
from maritime_swarm.ai_control.prompts import build_decision_system_prompt, build_decision_user_prompt
from maritime_swarm.ai_control.scene import Scene
from maritime_swarm.ai_control.tools import ToolContext, ToolRegistry
from maritime_swarm.llm.groq_client import inferenza_json

logger = logging.getLogger(__name__)

_MSG_TYPES = {"proposal", "ack", "objection", "handoff", "report", "status"}


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
    ) -> dict[str, Any]:
        ...


class GroqDecider:
    def __init__(self, api_key: str, model: str, temperature: float = 0.3) -> None:
        self.api_key, self.model, self.temperature = api_key, model, temperature

    def decide(self, obs, ctx, scene, mission, peers, shared_contacts, messages, current_task, registry):
        raw = inferenza_json(
            prompt=build_decision_user_prompt(obs, ctx, scene, mission, peers, shared_contacts, messages, current_task),
            api_key=self.api_key,
            system_prompt=build_decision_system_prompt(registry),
            model=self.model,
            temperature=self.temperature,
        )
        return normalise_decision(raw)


class HeuristicDecider:
    """Offline fallback: spread by id, investigate suspicious, hold otherwise.

    Not clever — only so the loop runs without an API key. Real behaviour comes
    from the LLM.
    """

    _SECTORS = ["NW", "NE", "SW", "SE"]

    def decide(self, obs, ctx, scene, mission, peers, shared_contacts, messages, current_task, registry):
        susp = [c for c in obs.contacts if c.is_suspicious]
        if susp:
            nearest = min(susp, key=lambda c: haversine_km(obs.lat, obs.lon, c.lat, c.lon))
            return normalise_decision({
                "reasoning": f"Suspicious contact {nearest.id} in range; closing to identify.",
                "messages": [{"to": "all", "type": "status", "content": f"Investigating {nearest.id}."}],
                "action": {"tool": "investigate_contact", "args": {"contact_id": nearest.id}},
            })
        idx = sum(ord(ch) for ch in ctx.agent_id) % len(self._SECTORS)
        return normalise_decision({
            "reasoning": "No contacts of interest; patrolling my sector for coverage.",
            "messages": [],
            "action": {"tool": "patrol_sector", "args": {"sector": self._SECTORS[idx]}},
        })
