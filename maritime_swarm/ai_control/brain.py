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
from maritime_swarm.ai_control.geo import haversine_km
from maritime_swarm.ai_control.observation import Observation
from maritime_swarm.ai_control.planner import AgentDecider
from maritime_swarm.ai_control.rate_limit import LLMGate
from maritime_swarm.ai_control.scene import POI as ScenePOI, Scene
from maritime_swarm.ai_control.tools import Tool, ToolContext, ToolError, ToolRegistry
from maritime_swarm.ai_control.world_client import WorldModelClient

logger = logging.getLogger(__name__)

STATUS_INTERVAL_S = 4.0      # world-time between status heartbeats
# Event-driven cadence: we re-think on EVENTS (new contact, peer message, mission
# change, action finished, idle) — NOT on a fixed timer while an action is still
# executing. The heartbeat is only a slow safety re-evaluation so a long-running
# action still gets reconsidered occasionally.
HEARTBEAT_S = 30.0             # slow fallback re-think while an action runs
MIN_DECISION_INTERVAL_S = 4.0  # floor: never think more often than this
RATE_LIMIT_COOLDOWN_S = 25.0   # back off this long after an LLM rate-limit (429)
# Movement tools — if one of these was the last action but the asset barely moved,
# the outcome feedback flags it (e.g. a go_to whose target was the current pos).
_MOVE_TOOLS = {"go_to", "move", "go_to_poi", "patrol_sector",
               "investigate_contact", "escort_contact", "visit_pois", "rendezvous"}
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
        decision_interval: float = HEARTBEAT_S,
        is_leader: bool = False,
        gate: LLMGate | None = None,
    ) -> None:
        self.client = client
        self.ctx = ctx
        self.decider = decider
        self.scene = scene
        # Only the lead asset adopts a mission at construction (it is the entry
        # point for the human's order). Peers start empty and learn the working
        # intent from the lead's briefing over the bus.
        self.mission = ((mission or "").strip() or None) if is_leader else None
        self.registry = registry
        self.decision_interval = decision_interval
        self.is_leader = is_leader
        self.gate = gate or LLMGate(min_spacing_s=0.0)

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
        self._brief_pending = False  # lead has a new/changed order it must brief peers on
        self._urgent = False         # a fresh contact needs an immediate decision
        self._epoch = 0              # bumped on reset; in-flight decisions from a
                                     # prior epoch are discarded when they return
        # Persistent self-authored plan + state for outcome feedback.
        self._plan: str | None = None
        self._decision_pos: tuple[float, float] | None = None  # pos when we last decided
        self._last_action_label: str | None = None             # what we last chose

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
                if msg.get("type") == "reset":
                    self._wipe()
                    continue
                if msg.get("type") != "observation":
                    continue
                await self._on_observation(Observation.from_payload(msg["payload"]))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[%s] loop ended: %s", self.ctx.agent_id, exc)
        finally:
            await self.client.close()

    def _wipe(self) -> None:
        """Drop ALL in-memory state back to fresh-boot defaults (on a reset).

        The world has been cleared and the engine paused; this ensures nothing
        from the previous run — mission, shared picture, active task, briefings,
        outbox — survives. The agent then idles until a new mission is issued.
        """
        self._epoch += 1  # invalidate any decision still in flight from before
        self.mission = None
        self.view = SwarmView(self.ctx.agent_id)
        self.active_tool = None
        self._action_spec = None
        self._current_task = None
        self._outbox = []
        self._brief_pending = False
        self._urgent = False
        self._seen_contacts = set()
        self._last_msg_count = 0
        self._dirty = True
        self._thinking = False
        self._last_status_t = -1e9
        self._plan = None
        self._decision_pos = None
        self._last_action_label = None
        logger.info("[%s] reset — wiped all state, idle until new mission", self.ctx.agent_id)

    async def _on_observation(self, obs: Observation) -> None:
        self.ctx.obs = obs
        self.ctx.view = self.view
        # Refresh the scene's POIs from the live observation so the agent reasons
        # over the CURRENT scenario's points of interest (buoy, rendezvous, …),
        # not the ones present when it first connected.
        if obs.pois:
            self.scene.pois = [
                ScenePOI(id=str(p.get("id", "")), label=str(p.get("label", "")),
                         lat=float((p.get("position") or {}).get("lat", 0.0)),
                         lon=float((p.get("position") or {}).get("lon", 0.0)))
                for p in obs.pois
            ]
        elif self.scene.pois:
            self.scene.pois = []
        # Keep the operating area in sync with the live selection so the agent
        # grounds "the area" / "the perimeter" in real geometry.
        self.scene.set_area_from_aor(obs.aor)
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
            # A contact just entered sensor range — react NOW: clear any 429
            # cooldown and bypass the min-decision interval so the asset doesn't
            # let a (possibly moving) contact drift back out before it responds.
            self._urgent = True
            self._cooldown_until = 0.0

        # status heartbeat (always — keeps peer awareness alive even while idle)
        await self._maybe_broadcast_status(obs)

        # mission set / changed / cleared
        if not self._handle_mission(obs):
            return

        # EVENT-DRIVEN decision. Re-think only when something has changed (new
        # contact / peer message / mission), when we're idle (no active action to
        # run), or on a slow heartbeat — NOT on a fast timer while an action is
        # still executing. This is what stops the hold↔go_to oscillation: once an
        # agent commits to a move, it lets it run until it arrives or an event
        # interrupts, instead of re-deciding (and flip-flopping) every few seconds.
        now = time.monotonic()
        has_action = self.active_tool is not None
        heartbeat_due = (now - self._last_decision) >= self.decision_interval
        due = self._dirty or (not has_action) or heartbeat_due
        min_gap = 0.0 if self._urgent else MIN_DECISION_INTERVAL_S
        if (not self._thinking and due and now >= self._cooldown_until
                and (now - self._last_decision) >= min_gap):
            self._thinking = True
            self._dirty = False
            urgent = self._urgent
            self._urgent = False
            asyncio.create_task(self._think(obs, urgent))

        # execute the active tool
        await self._execute(obs)

    # ── mission ──────────────────────────────────────────────────────────────
    def _handle_mission(self, obs: Observation) -> bool:
        """Track the working intent and return whether the agent has one.

        The LEAD asset reads the human's order from its observation. PEERS never
        see that text — their working intent is whatever the lead briefed them
        over the bus (the 'intent' message, captured in the SwarmView).
        """
        if self.is_leader:
            incoming = (obs.mission or "").strip()
            adopt_label = "new order — interpreting & briefing peers"
        else:
            incoming = (self.view.briefed_intent or "").strip()
            adopt_label = "adopted lead's briefed intent"

        if incoming != (self.mission or ""):
            if incoming:
                self.mission = incoming
                self._dirty = True
                if self.is_leader:
                    self._brief_pending = True  # must re-brief peers this think cycle
                logger.info("[%s] %s: %s", self.ctx.agent_id, adopt_label, incoming)
                asyncio.create_task(self.client.send_cot(f"\n[{adopt_label}] {incoming}\n"))
            else:
                self.mission = None
                self.active_tool = None
                self._action_spec = None
                logger.info("[%s] no active intent — holding.", self.ctx.agent_id)
                asyncio.create_task(self.client.send_cot("No active intent — holding station.\n"))
                asyncio.create_task(self.client.send_action(
                    {"speed_kn": 0.0, "planned_path": [], "current_task": "Idle — awaiting orders"}))
                # When the human clears the order, the lead stands the team down
                # over the bus so peers (who never saw the order) also hold.
                if self.is_leader:
                    asyncio.create_task(self.client.send_p2p(
                        "all", "intent", {"text": "STAND DOWN — order cleared; hold station."},
                        reasoning="Order cleared by operator."))
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
    def _build_feedback(self, obs: Observation) -> str:
        """Plain-language outcome of the last decision: did we move, where are we
        against our task. Lets the model self-correct from consequences instead of
        being told rules (e.g. it sees a go_to that produced no movement)."""
        parts: list[str] = []
        if self._last_action_label:
            parts.append(f"last action: {self._last_action_label}")
        if self._decision_pos is not None:
            moved_km = haversine_km(self._decision_pos[0], self._decision_pos[1], obs.lat, obs.lon)
            parts.append("you moved " + (f"{moved_km * 1000:.0f} m" if moved_km < 1.0 else f"{moved_km:.1f} km")
                         + " since then")
            label = self._last_action_label or ""
            if moved_km < 0.03 and any(label.startswith(t) for t in _MOVE_TOOLS):
                parts.append("you barely moved — your target may equal your current position or you're "
                             "blocked; choose a DIFFERENT target if you meant to reposition")
        parts.append(f"current task: {self._current_task or 'idle'}")
        return "; ".join(parts)

    def _context(self) -> tuple[list, list, list]:
        peers = [{"id": pid, "type": p.agent_type, "lat": p.lat, "lon": p.lon, "task": p.task}
                 for pid in self.view.live_peer_ids() if (p := self.view.peers.get(pid))]
        shared = [{"id": cid, "label": sc.label, "flagged": sc.flagged, "reported": sc.reported,
                   "lat": sc.lat, "lon": sc.lon} for cid, sc in self.view.contacts.items()]
        messages = [{"sender": m.sender, "type": m.msg_type, "text": m.text}
                    for m in self.view.recent_messages(8)]
        return peers, shared, messages

    async def _think(self, obs: Observation, urgent: bool = False) -> None:
        try:
            my_epoch = self._epoch  # if a reset bumps this, discard our result
            peers, shared, messages = self._context()
            task_status = "executing" if self.active_tool is not None else "idle"
            silent = self.view.silent_peer_ids()

            # Stream the reasoning prose into the CoT panel live (token-by-token).
            # decide() runs in a worker thread, so push each token back onto the
            # event loop thread-safely. Tokens are dropped if a reset has since
            # happened, so a stale in-flight decision can't write to the panel.
            loop = asyncio.get_running_loop()

            def emit(token: str) -> None:
                if self._epoch != my_epoch:
                    return
                try:
                    asyncio.run_coroutine_threadsafe(self.client.send_cot(token), loop)
                except RuntimeError:  # loop shutting down
                    pass

            feedback = self._build_feedback(obs)

            # The swarm-wide gate serialises and spaces LLM calls so three agents
            # share the Groq token budget fairly instead of one starving the rest.
            async with self.gate.slot(self.ctx.agent_id, urgent=urgent):
                d = await asyncio.to_thread(
                    self.decider.decide, obs, self.ctx, self.scene, self.mission,
                    peers, shared, messages, self._current_task, self.registry,
                    task_status, silent, list(self._outbox), self.is_leader, emit,
                    self._plan, feedback)

            # A reset happened while this decision was in flight (LLM latency):
            # drop it entirely so it can't move the agent or re-populate state.
            if self._epoch != my_epoch:
                logger.info("[%s] discarding stale decision (reset during think)", self.ctx.agent_id)
                return

            await self.client.send_cot("\n")  # terminate this cycle's streamed line

            # Carry the agent's self-authored plan forward to the next turn, and
            # record where we were when we decided (for movement feedback).
            if d.get("plan"):
                self._plan = d["plan"]
            self._decision_pos = (obs.lat, obs.lon)

            for m in d["messages"]:
                await self.client.send_p2p(m["to"], m["type"], {"text": m["content"]}, reasoning=m["content"])
                self._outbox.append(m)
                self._outbox = self._outbox[-5:]

            reasoning = d.get("reasoning") or ""

            # Guarantee the lead briefs its peers when the order is new/changed:
            # if the model didn't emit an 'intent' message itself this cycle, send
            # one synthesised from the lead's own reasoning (its interpretation —
            # still re-expressed, never the verbatim order). Without this, peers
            # can stay stuck on a stale briefing while the lead acts alone.
            if self._brief_pending:
                if not any(m.get("type") == "intent" for m in d["messages"]):
                    brief = reasoning.strip() or self.mission or ""
                    if brief:
                        await self.client.send_p2p(
                            "all", "intent", {"text": brief}, reasoning=brief)
                self._brief_pending = False

            tool_name = (d.get("tool") or "").strip()
            if tool_name.lower() in _NO_OP_TOOLS:
                logger.info("[%s] decision: continue | %s", self.ctx.agent_id, reasoning[:80])
            else:
                spec = (tool_name, d.get("args") or {})
                if spec != self._action_spec:
                    try:
                        self.active_tool = self.registry.build(spec[0], spec[1], self.ctx)
                        self._action_spec = spec
                        self._last_action_label = f"{spec[0]}({', '.join(str(v) for v in spec[1].values())})"
                        logger.info("[%s] decision: %s | %s",
                                    self.ctx.agent_id, self.active_tool.describe(), reasoning[:80])
                    except ToolError as exc:
                        logger.info("[%s] tool rejected (%s) — keeping current", self.ctx.agent_id, exc)
        except Exception as exc:
            if "429" in str(exc):
                # Honour the server's Retry-After when present so we surface the
                # real budget-reset window (the Groq ~6000 TPM / 500k TPD cap is
                # the dominant constraint) instead of guessing a flat cooldown.
                cooldown = RATE_LIMIT_COOLDOWN_S
                resp = getattr(exc, "response", None)
                retry_after = resp.headers.get("retry-after") if resp is not None else None
                if retry_after:
                    try:
                        cooldown = max(cooldown, float(retry_after))
                    except ValueError:
                        pass
                self._cooldown_until = time.monotonic() + cooldown
                logger.info("[%s] rate-limited (429) — backing off %.0fs%s", self.ctx.agent_id,
                            cooldown, f" (Retry-After={retry_after})" if retry_after else "")
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
