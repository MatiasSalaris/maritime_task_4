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
from maritime_swarm.ai_control.rate_limit import NullLimiter
from maritime_swarm.ai_control.scene import Scene
from maritime_swarm.ai_control.tools import Tool, ToolContext, ToolError, ToolRegistry
from maritime_swarm.ai_control.world_client import WorldModelClient

logger = logging.getLogger(__name__)

STATUS_INTERVAL_S = 4.0      # world-time between status heartbeats
# Event-driven thinking: react fast to events (a peer message, a new contact, a
# finished task, a mission change) but only poll slowly when nothing changes.
# This is responsive where it matters AND frugal with the LLM token budget.
# Token-bucket reality (Groq free tier ≈ 6000 tokens/min, refilling ~100/s):
# bursts are fine, only the sustained average matters. So respond fast to EVENTS
# (~5s) but keep the IDLE heartbeat long so steady-state stays cheap and never
# drains the bucket into a lockout.
DECISION_INTERVAL_S = 45.0   # idle heartbeat — re-think this often with no events
MIN_DECISION_INTERVAL_S = 5.0  # floor between decisions (event responsiveness)
RATE_LIMIT_COOLDOWN_S = 8.0   # fallback backoff if a 429 carries no retry-after
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
        limiter=None,
    ) -> None:
        self.client = client
        self.ctx = ctx
        self.decider = decider
        self.base_scene = scene
        self.scene = scene
        self.mission = (mission or "").strip() or None
        self.registry = registry
        self.decision_interval = decision_interval
        self.limiter = limiter or NullLimiter()

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
        self._aor_signature: str | None = None
        self._mission_complete_contact: str | None = None

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
        self._refresh_scene_from_observation(obs)
        self.ctx.scene = self.scene
        self.ctx.bounds = self.scene.bounds
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

        if await self._maybe_stop_for_completed_mission(obs):
            return
        if await self._maybe_complete_buoy_mission(obs):
            return

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
                self.active_tool = None
                self._action_spec = None
                self._current_task = "Ricalcolo missione"
                self._dirty = True
                self._last_decision = 0.0
                self._outbox.clear()
                self._mission_complete_contact = None
                logger.info("[%s] new mission: %s", self.ctx.agent_id, incoming)
                asyncio.create_task(self.client.send_cot(f"New mission — re-thinking: {incoming}\n"))
                asyncio.create_task(self.client.send_action({
                    "speed_kn": 0.0,
                    "planned_path": [],
                    "current_task": self._current_task,
                }))
            else:
                self.mission = None
                self.active_tool = None
                self._action_spec = None
                self._mission_complete_contact = None
                logger.info("[%s] mission cleared — holding.", self.ctx.agent_id)
                asyncio.create_task(self.client.send_cot("Mission cleared — holding station.\n"))
                asyncio.create_task(self.client.send_action(
                    {"speed_kn": 0.0, "planned_path": [], "current_task": "Idle — awaiting orders"}))
        return self.mission is not None

    async def _maybe_stop_for_completed_mission(self, obs: Observation) -> bool:
        if obs.mission_status != "completed":
            return False
        contact_id = str((obs.mission_result or {}).get("contact_id") or "target")
        if self._mission_complete_contact == contact_id:
            return True
        self._mission_complete_contact = contact_id
        self.active_tool = None
        self._action_spec = None
        self._dirty = False
        self._current_task = f"Missione completata: boa {contact_id} trovata"
        await self.client.send_action({
            "speed_kn": 0.0,
            "planned_path": [],
            "current_task": self._current_task,
        })
        await self.client.send_cot(f"Missione completata: boa {contact_id} trovata.\n")
        logger.info("[%s] mission already completed: %s", self.ctx.agent_id, contact_id)
        return True

    async def _maybe_complete_buoy_mission(self, obs: Observation) -> bool:
        if not self.mission:
            return False
        mission_l = self.mission.lower()
        if not any(word in mission_l for word in ("buoy", "boa")):
            return False

        contact_id = None
        for c in obs.contacts:
            if c.is_buoy:
                contact_id = c.id
                break
        if contact_id is None:
            for cid, sc in self.view.contacts.items():
                if sc.label.upper() == "BUOY" or cid.lower().startswith("buoy"):
                    contact_id = cid
                    break
        if contact_id is None:
            return False

        if self._mission_complete_contact == contact_id:
            return True

        own_contact = next((c for c in obs.contacts if c.id == contact_id), None)
        shared_contact = self.view.contacts.get(contact_id)
        lat = own_contact.lat if own_contact else (shared_contact.lat if shared_contact else obs.lat)
        lon = own_contact.lon if own_contact else (shared_contact.lon if shared_contact else obs.lon)

        self._mission_complete_contact = contact_id
        self.active_tool = None
        self._action_spec = None
        self._dirty = False
        self._current_task = f"Missione completata: boa {contact_id} trovata"
        await self.client.send_action({
            "speed_kn": 0.0,
            "planned_path": [],
            "current_task": self._current_task,
        })
        await self.client.send_p2p("all", "report", {
            "text": f"Boa {contact_id} trovata. Interrompo la ricerca.",
            "contacts": [{
                "id": contact_id,
                "lat": lat,
                "lon": lon,
                "label": "BUOY",
                "reported": True,
            }],
        }, reasoning=f"Boa {contact_id} trovata: ricerca terminata per tutti gli agenti.")
        if own_contact is not None:
            await self.client.send_mission_complete({
                "status": "success",
                "reason": "missing_buoy_found",
                "contact_id": contact_id,
                "label": "BUOY",
                "lat": lat,
                "lon": lon,
                "completed_by": self.ctx.agent_id,
                "completed_by_name": self.ctx.agent_name,
                "mission": self.mission,
            })
        await self.client.send_cot(f"Boa {contact_id} trovata: ricerca interrotta.\n")
        logger.info("[%s] buoy mission complete: %s", self.ctx.agent_id, contact_id)
        return True

    def _refresh_scene_from_observation(self, obs: Observation) -> None:
        sig = repr(obs.aor) if obs.aor else None
        if sig == self._aor_signature:
            return
        self._aor_signature = sig
        self.scene = self.base_scene.with_aor(obs.aor) if obs.aor else self.base_scene
        self.ctx.bounds = self.scene.bounds
        self.ctx.scene = self.scene
        self._dirty = True
        if obs.aor:
            logger.info("[%s] selected AOR updated: lat %.3f..%.3f lon %.3f..%.3f",
                        self.ctx.agent_id, self.scene.bounds.lat_min, self.scene.bounds.lat_max,
                        self.scene.bounds.lon_min, self.scene.bounds.lon_max)

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
            # Pace against the shared token budget so 3 agents never burst the
            # provider's per-minute limit into a lockout.
            await self.limiter.acquire(1300)
            d = await asyncio.to_thread(
                self.decider.decide, obs, self.ctx, self.scene, self.mission,
                peers, shared, messages, self._current_task, self.registry,
                task_status, silent, list(self._outbox))

            reasoning = d.get("reasoning") or ""
            for m in d["messages"]:
                await self.client.send_p2p(m["to"], m["type"], {"text": m["content"]}, reasoning=reasoning)
                self._outbox.append(m)
                self._outbox = self._outbox[-5:]

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
            resp = getattr(exc, "response", None)
            status = getattr(resp, "status_code", None)
            if status == 429 or "429" in str(exc):
                retry = None
                if resp is not None:
                    try:
                        retry = float(resp.headers.get("retry-after"))
                    except (TypeError, ValueError):
                        retry = None
                backoff = retry if retry else RATE_LIMIT_COOLDOWN_S
                self._cooldown_until = time.monotonic() + backoff
                logger.info("[%s] rate-limited (429) — backing off %.1fs", self.ctx.agent_id, backoff)
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
