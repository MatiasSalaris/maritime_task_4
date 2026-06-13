"""The per-agent open-ended decision/execution loop.

Each asset runs this independently. There is no leader and no central plan.
Every few seconds (or on an event), the agent calls its LLM once with the full
situation — mission, what it senses, the shared picture and its peers' messages
— and gets back: reasoning, any coordination messages, and a single action.
Coordination emerges from the messages the agents exchange; convergence comes
from the social conventions in the prompt, not from code.

Between decisions the chosen tool runs tick-by-tick. Status is broadcast
continuously so peers keep a shared picture.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from maritime_swarm.ai_control.blackboard import SwarmView
from maritime_swarm.ai_control.observation import Observation
from maritime_swarm.ai_control.planner import AgentDecider
from maritime_swarm.ai_control.scene import Scene
from maritime_swarm.ai_control.tools import Tool, ToolContext, ToolError, ToolRegistry
from maritime_swarm.ai_control.world_client import WorldModelClient

logger = logging.getLogger(__name__)

STATUS_INTERVAL_S = 4.0      # world-time between status heartbeats
DECISION_INTERVAL_S = 10.0   # think at least this often (wall clock)
MIN_DECISION_INTERVAL_S = 6.0  # never think more often than this
RATE_LIMIT_COOLDOWN_S = 25.0  # back off this long after an LLM rate-limit (429)
_NO_OP_TOOLS = {"", "continue", "none", "keep", "hold_current"}


class AgentBrain:
    def __init__(
        self,
        client: WorldModelClient,
        ctx: ToolContext,
        decider: AgentDecider,
        scene: Scene,
        mission: str | None,
        registry: ToolRegistry,
        decision_interval: float = DECISION_INTERVAL_S,
    ) -> None:
        self.client = client
        self.ctx = ctx
        self.decider = decider
        self.scene = scene
        self.mission = (mission or "").strip() or None
        self.registry = registry
        self.decision_interval = decision_interval

        self.view = SwarmView(ctx.agent_id)
        self.active_tool: Tool | None = None
        self._action_spec: tuple[str, dict[str, Any]] | None = None
        self._current_task: str | None = None

        self._last_status_t = -1e9
        self._last_decision = 0.0
        self._thinking = False
        self._dirty = True
        self._last_msg_count = 0
        self._seen_contacts: set[str] = set()
        self._cooldown_until = 0.0   # set after a 429 to avoid hammering the API
        self._outbox: list[dict[str, Any]] = []   # recent messages we sent (own state)

    # ── main loop ──────────────────────────────────────────────────────────
    async def run(self) -> None:
        await self.client.connect()
        await self.client.send_cot(f"{self.ctx.agent_name} online.\n")
        # Stagger the agents' first decisions so three LLM calls don't burst at
        # once (avoids an immediate rate-limit spike).
        idx = next((int(ch) for ch in reversed(self.ctx.agent_id) if ch.isdigit()), 0)
        self._cooldown_until = time.monotonic() + idx * 3.0
        try:
            while True:
                msg = await self.client.recv()
                if msg.get("type") != "observation":
                    continue
                await self._on_observation(Observation.from_payload(msg["payload"]))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[%s] loop ended: %s", self.ctx.agent_id, exc)
        finally:
            await self.client.close()

    async def _on_observation(self, obs: Observation) -> None:
        self.ctx.obs = obs
        self.ctx.view = self.view
        self.ctx.scene = self.scene
        self.view.tick(obs.world_time)

        # ingest peer traffic + our own sightings into the shared picture
        for m in obs.inbox:
            self.view.ingest(m.get("from_agent", ""), m.get("msg_type", ""),
                             m.get("content", {}) or {}, m.get("reasoning"))
        self.view.observe(obs.contacts)

        # event triggers → think sooner
        if len(self.view.messages) != self._last_msg_count:
            self._last_msg_count = len(self.view.messages)
            self._dirty = True
        new_ids = {c.id for c in obs.contacts} - self._seen_contacts
        if new_ids:
            self._seen_contacts |= new_ids
            self._dirty = True

        # status heartbeat (always — keeps peer awareness alive even while idle)
        await self._maybe_broadcast_status(obs)

        # mission set / changed / cleared
        if not self._handle_mission(obs):
            return

        # decide (LLM) on interval or event, honouring any rate-limit cooldown
        now = time.monotonic()
        due = self._dirty or (now - self._last_decision) >= self.decision_interval
        if (not self._thinking and due and now >= self._cooldown_until
                and (now - self._last_decision) >= MIN_DECISION_INTERVAL_S):
            self._thinking = True
            self._dirty = False
            asyncio.create_task(self._think(obs))

        # execute the active tool
        await self._execute(obs)

    # ── mission ──────────────────────────────────────────────────────────────
    def _handle_mission(self, obs: Observation) -> bool:
        incoming = (obs.mission or "").strip()
        if incoming != (self.mission or ""):
            if incoming:
                self.mission = incoming
                self._dirty = True
                self._outbox.clear()
                logger.info("[%s] new mission: %s", self.ctx.agent_id, incoming)
                asyncio.create_task(self.client.send_cot(f"New mission — re-thinking: {incoming}\n"))
            else:
                self.mission = None
                self.active_tool = None
                self._action_spec = None
                logger.info("[%s] mission cleared — holding.", self.ctx.agent_id)
                asyncio.create_task(self.client.send_cot("Mission cleared — holding station.\n"))
                asyncio.create_task(self.client.send_action(
                    {"speed_kn": 0.0, "planned_path": [], "current_task": "Idle — awaiting orders"}))
        return self.mission is not None

    # ── status ─────────────────────────────────────────────────────────────
    async def _maybe_broadcast_status(self, obs: Observation) -> None:
        if (obs.world_time - self._last_status_t) < STATUS_INTERVAL_S:
            return
        self._last_status_t = obs.world_time
        await self.client.send_p2p("all", "status", {
            "name": self.ctx.agent_name, "type": self.ctx.agent_type,
            "pos": {"lat": obs.lat, "lon": obs.lon}, "heading": obs.heading, "speed_kn": obs.speed_kn,
            "task": self._current_task,
            "contacts": [{"id": c.id, "lat": c.lat, "lon": c.lon, "label": c.label, "flagged": c.flagged}
                         for c in obs.contacts],
        })

    # ── decision ─────────────────────────────────────────────────────────────
    def _context(self) -> tuple[list, list, list]:
        peers = [{"id": pid, "type": p.agent_type, "lat": p.lat, "lon": p.lon, "task": p.task}
                 for pid in self.view.live_peer_ids() if (p := self.view.peers.get(pid))]
        shared = [{"id": cid, "label": sc.label, "flagged": sc.flagged, "reported": sc.reported,
                   "lat": sc.lat, "lon": sc.lon} for cid, sc in self.view.contacts.items()]
        messages = [{"sender": m.sender, "type": m.msg_type, "text": m.text}
                    for m in self.view.recent_messages(8)]
        return peers, shared, messages

    async def _think(self, obs: Observation) -> None:
        try:
            peers, shared, messages = self._context()
            task_status = "executing" if self.active_tool is not None else "idle"
            silent = self.view.silent_peer_ids()
            d = await asyncio.to_thread(
                self.decider.decide, obs, self.ctx, self.scene, self.mission,
                peers, shared, messages, self._current_task, self.registry,
                task_status, silent, list(self._outbox))

            for m in d["messages"]:
                await self.client.send_p2p(m["to"], m["type"], {"text": m["content"]}, reasoning=m["content"])
                self._outbox.append(m)
                self._outbox = self._outbox[-5:]

            reasoning = d.get("reasoning") or ""
            if reasoning:
                await self.client.send_cot(reasoning + "\n")

            tool_name = (d.get("tool") or "").strip()
            if tool_name.lower() in _NO_OP_TOOLS:
                logger.info("[%s] decision: continue | %s", self.ctx.agent_id, reasoning[:80])
            else:
                spec = (tool_name, d.get("args") or {})
                if spec != self._action_spec:
                    try:
                        self.active_tool = self.registry.build(spec[0], spec[1], self.ctx)
                        self._action_spec = spec
                        logger.info("[%s] decision: %s | %s",
                                    self.ctx.agent_id, self.active_tool.describe(), reasoning[:80])
                    except ToolError as exc:
                        logger.info("[%s] tool rejected (%s) — keeping current", self.ctx.agent_id, exc)
        except Exception as exc:
            if "429" in str(exc):
                self._cooldown_until = time.monotonic() + RATE_LIMIT_COOLDOWN_S
                logger.info("[%s] rate-limited (429) — backing off %.0fs", self.ctx.agent_id, RATE_LIMIT_COOLDOWN_S)
            else:
                logger.warning("[%s] decider error: %s", self.ctx.agent_id, exc)
        finally:
            self._last_decision = time.monotonic()
            self._thinking = False

    # ── execution ──────────────────────────────────────────────────────────
    async def _execute(self, obs: Observation) -> None:
        if self.active_tool is None:
            return
        inv = self.active_tool.step(obs, self.ctx)
        if inv.action is not None:
            self._current_task = inv.action.get("current_task", self._current_task)
            await self.client.send_action(inv.action)
        if inv.p2p is not None:
            await self.client.send_p2p(
                inv.p2p.get("to", "all"), inv.p2p.get("msg_type", "status"),
                inv.p2p.get("content", {}), reasoning=inv.p2p.get("reasoning"))
        if inv.finished:
            # task done/failed → free up and re-decide next cycle
            self.active_tool = None
            self._action_spec = None
            self._dirty = True
