"""The per-agent decision/execution loop — now coordinated and grounded.

Each agent:
  • receives observations (~10 Hz) and ingests peer messages into its own
    SwarmView (shared situational picture), built only from the P2P bus;
  • broadcasts its status periodically so peers know it and the contacts it sees;
  • participates in an emergent negotiation — the lowest-id live asset acts as
    leader, interprets the mission and broadcasts a proposed allocation; peers
    adopt and acknowledge. A deterministic de-confliction runs locally in every
    agent as a convergence backstop (no central authority);
  • runs its assigned baseline task (patrol sector / escort / visit POIs …)
    deterministically, and consults the tactician LLM only to *react* to sensed
    contacts (investigate / report).

There is no central planner: strategy is proposed by a peer and can be taken
over by another peer if the leader goes silent.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

from maritime_swarm.ai_control.blackboard import PeerInfo, SwarmView
from maritime_swarm.ai_control.coordination import (
    assignment_label,
    default_allocation,
    deconflict,
)
from maritime_swarm.ai_control.geo import destination, haversine_km
from maritime_swarm.ai_control.observation import Observation
from maritime_swarm.ai_control.planner import TacticalPlanner
from maritime_swarm.ai_control.scene import Scene
from maritime_swarm.ai_control.strategist import HeuristicStrategist, Strategist
from maritime_swarm.ai_control.tools import Tool, ToolContext, ToolError, ToolRegistry, ToolStatus
from maritime_swarm.ai_control.world_client import WorldModelClient

logger = logging.getLogger(__name__)

STATUS_INTERVAL_S = 4.0       # world-time between status broadcasts
NEGOTIATION_GRACE_S = 3.0     # wait this long (world time) before leading, so peers are known
REACTIVE_INTERVAL_S = 4.0     # min wall-clock between tactician LLM calls
_FOLLOW_WORDS = ("follow", "shadow", "escort", "track", "tail", "trail")
# Missions that direct the team onto a discovered TARGET. These must be about
# intercepting/converging on a contact — NOT generic team orders like
# "everybody head south" (which has nothing to do with a target).
_CONVERGE_WORDS = ("converge", "intercept", "rendezvous with", "close on", "all intercept")
# Directional team orders: a movement verb + a compass direction.
_MOVE_VERBS = ("go", "head", "move", "proceed", "turn", "sail", "transit", "steer", "advance", "reposition")
_DIRECTIONS = {
    "north": 0, "northeast": 45, "north-east": 45, "east": 90, "southeast": 135, "south-east": 135,
    "south": 180, "southwest": 225, "south-west": 225, "west": 270, "northwest": 315, "north-west": 315,
}
_CARDINAL = {0: "north", 45: "NE", 90: "east", 135: "SE", 180: "south", 225: "SW", 270: "west", 315: "NW"}


class AgentBrain:
    def __init__(
        self,
        client: WorldModelClient,
        ctx: ToolContext,
        strategist: Strategist,
        tactician: TacticalPlanner,
        scene: Scene,
        mission: str | None,
        registry: ToolRegistry,
    ) -> None:
        self.client = client
        self.ctx = ctx
        self.strategist = strategist
        self.tactician = tactician
        self.scene = scene
        self.mission = (mission or "").strip() or None
        self.registry = registry

        self.view = SwarmView(ctx.agent_id)
        self.brief: dict[str, Any] | None = None
        self.assignment: dict[str, Any] | None = None
        self._assignment_label = "UNASSIGNED"
        self.baseline_tool: Tool | None = None
        self.reactive_tool: Tool | None = None

        self._t0: float | None = None
        self._last_status_t = -1e9
        self._current_task: str | None = None
        self._negotiated_for: str | None = None
        self._planned_roster: set[str] = set()
        self._planned_engaged: frozenset[str] = frozenset()
        self._planned_targets: frozenset[str] = frozenset()
        self._thinking_strategy = False
        self._thinking_reactive = False
        self._last_reactive_think = 0.0
        self._handled: set[str] = set()   # contacts already reported or being followed
        self._pending_report: dict[str, Any] | None = None   # a just-identified contact
        self._dynamic_assignment: dict[str, Any] | None = None   # reactive override (e.g. escort)

    # ── main loop ──────────────────────────────────────────────────────────
    async def run(self) -> None:
        await self.client.connect()
        await self.client.send_cot(f"{self.ctx.agent_name} online.\n")
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
        if self._t0 is None:
            self._t0 = obs.world_time
        self.ctx.obs = obs
        self.ctx.view = self.view
        self.ctx.scene = self.scene
        self.view.tick(obs.world_time)

        # 1) ingest peer messages + our own sightings into the shared picture
        for m in obs.inbox:
            self.view.ingest(m.get("from_agent", ""), m.get("msg_type", ""), m.get("content", {}) or {})
        self.view.observe(obs.contacts)

        # 2) broadcast our status ALWAYS (even while idle) so peer awareness and
        #    leader election stay stable across idle periods.
        await self._maybe_broadcast_status(obs)

        # 3) mission set / change / clear
        if not self._handle_mission(obs):
            return  # mission cleared → idling

        # 4) emergent negotiation (leader proposes; peers adopt)
        self._maybe_negotiate(obs)

        # 5) adopt our assignment (with local de-confliction backstop)
        await self._refresh_assignment(obs)

        # 6) react to sensed contacts (tactician LLM)
        self._maybe_react(obs)

        # 7) execute the active tool
        await self._execute(obs)

    # ── mission ──────────────────────────────────────────────────────────────
    def _handle_mission(self, obs: Observation) -> bool:
        incoming = (obs.mission or "").strip()
        if incoming != (self.mission or ""):
            if incoming:
                self.mission = incoming
                self.brief = None
                self.assignment = None
                self.baseline_tool = None
                self.reactive_tool = None
                self._negotiated_for = None
                self._handled.clear()
                self._dynamic_assignment = None
                logger.info("[%s] new mission: %s", self.ctx.agent_id, incoming)
                asyncio.create_task(self.client.send_cot(f"New mission — re-planning: {incoming}\n"))
            else:
                self.mission = None
                self.assignment = None
                self.baseline_tool = None
                self.reactive_tool = None
                self._dynamic_assignment = None
                self._handled.clear()
                self.view.allocation = {}
                logger.info("[%s] mission cleared — holding.", self.ctx.agent_id)
                asyncio.create_task(self.client.send_cot("Mission cleared — holding station.\n"))
                asyncio.create_task(self.client.send_action(
                    {"speed_kn": 0.0, "planned_path": [], "current_task": "Idle — awaiting orders"}))
        return self.mission is not None

    # ── status broadcast ───────────────────────────────────────────────────
    async def _maybe_broadcast_status(self, obs: Observation) -> None:
        if (obs.world_time - self._last_status_t) < STATUS_INTERVAL_S:
            return
        self._last_status_t = obs.world_time
        content = {
            "name": self.ctx.agent_name,
            "type": self.ctx.agent_type,
            "pos": {"lat": obs.lat, "lon": obs.lon},
            "heading": obs.heading,
            "speed_kn": obs.speed_kn,
            "task": self._current_task,
            "assignment": self.assignment,
            "contacts": [
                {"id": c.id, "lat": c.lat, "lon": c.lon, "label": c.label, "flagged": c.flagged}
                for c in obs.contacts
            ],
        }
        await self.client.send_p2p("all", "status", content)

    # ── negotiation ────────────────────────────────────────────────────────
    def _members(self, obs: Observation) -> list[dict[str, Any]]:
        members = [{
            "id": self.ctx.agent_id, "name": self.ctx.agent_name,
            "type": self.ctx.agent_type, "lat": obs.lat, "lon": obs.lon, "is_self": True,
        }]
        for pid in self.view.live_peer_ids():
            p = self.view.peers[pid]
            members.append({"id": pid, "name": p.name or pid, "type": p.agent_type or "?",
                            "lat": p.lat, "lon": p.lon})
        return members

    def _is_leader(self) -> bool:
        live = self.view.live_member_ids()
        return bool(live) and live[0] == self.ctx.agent_id

    def _engaged_map(self) -> dict[str, dict[str, Any]]:
        """Agents (self + live peers) committed to a non-patrol task (e.g. escort)."""
        engaged: dict[str, dict[str, Any]] = {}
        if self.assignment and (self.assignment.get("kind") or "") == "escort":
            engaged[self.ctx.agent_id] = self.assignment
        for pid in self.view.live_peer_ids():
            a = self.view.peers[pid].assignment
            if a and (a.get("kind") or "") == "escort":
                engaged[pid] = a
        return engaged

    def _is_converge_mission(self) -> bool:
        return any(w in (self.mission or "").lower() for w in _CONVERGE_WORDS)

    def _directional_order(self) -> tuple[float, float] | None:
        """Parse a 'go/head <dist> <direction>' team order → (bearing_deg, dist_km)."""
        t = (self.mission or "").lower()
        if not any(re.search(r"\b" + v + r"\b", t) for v in _MOVE_VERBS):
            return None
        bearing = None
        for name in sorted(_DIRECTIONS, key=len, reverse=True):
            if re.search(r"\b" + re.escape(name) + r"\b", t):
                bearing = _DIRECTIONS[name]
                break
        if bearing is None:
            return None
        dm = re.search(r"(\d+(?:\.\d+)?)\s*km", t)
        return (float(bearing), float(dm.group(1)) if dm else 5.0)

    def _known_target_ids(self) -> frozenset[str]:
        """Suspicious (flagged / UNKNOWN) contacts in the shared picture."""
        return frozenset(
            cid for cid, sc in self.view.contacts.items()
            if sc.flagged or (sc.label or "").upper() == "UNKNOWN")

    def _converge_target(self, obs: Observation) -> str | None:
        """For a 'whole team converge/intercept' mission, the target to send all to."""
        if not self._is_converge_mission():
            return None
        cands = [(cid, sc) for cid, sc in self.view.contacts.items()
                 if sc.flagged or (sc.label or "").upper() == "UNKNOWN"]
        if not cands:
            return None
        return min(cands, key=lambda kv: haversine_km(obs.lat, obs.lon, kv[1].lat, kv[1].lon))[0]

    def _maybe_negotiate(self, obs: Observation) -> None:
        if self._thinking_strategy or self._t0 is None:
            return
        grace_passed = (obs.world_time - self._t0) >= NEGOTIATION_GRACE_S
        if not grace_passed:
            return
        if not self._is_leader():
            return
        roster = set(self.view.live_member_ids())
        engaged = frozenset(self._engaged_map())
        # For a converge/intercept mission, the discovery of the target is itself
        # a reason to re-plan and send the whole team to it.
        targets = self._known_target_ids() if self._is_converge_mission() else frozenset()
        need = (
            self._negotiated_for != self.mission
            or roster != self._planned_roster
            or engaged != self._planned_engaged
            or targets != self._planned_targets
        )
        if not need:
            return
        self._thinking_strategy = True
        self._negotiated_for = self.mission
        self._planned_roster = roster
        self._planned_engaged = engaged
        self._planned_targets = targets
        asyncio.create_task(self._run_strategy(obs))

    async def _run_strategy(self, obs: Observation) -> None:
        try:
            members = self._members(obs)

            # Directional team order ('everybody go 5 km south') → send every asset
            # to a computed waypoint. Deterministic, overrides any engagement.
            direction = self._directional_order()
            if direction is not None:
                bearing, dist = direction
                allocation: dict[str, dict[str, Any]] = {}
                for m in members:
                    dlat, dlon = destination(m["lat"], m["lon"], bearing, dist)
                    if self.scene.bounds:
                        dlat, dlon = self.scene.bounds.clamp_point(dlat, dlon)
                    allocation[m["id"]] = {"kind": "go_to", "lat": dlat, "lon": dlon}
                brief = {"objective": self.mission, "constraints": [], "priority": None}
                self.brief = brief
                self.view.brief = brief
                self.view.allocation = allocation
                self.view.last_proposal_t = obs.world_time
                reasoning = f"Team order — all assets proceed {dist:.0f} km {_CARDINAL.get(bearing, '')}."
                await self.client.send_p2p("all", "proposal", {"brief": brief, "allocation": allocation},
                                           reasoning=reasoning)
                await self.client.send_cot(f"Plan: {reasoning}\n")
                logger.info("[%s] (leader) directional order: %s km bearing %.0f",
                            self.ctx.agent_id, dist, bearing)
                return

            engaged = self._engaged_map()
            # Divide the area only among the un-engaged assets; keep the engaged
            # ones on their current task.
            to_allocate = [m for m in members if m["id"] not in engaged] or members
            engaged_labels = {aid: assignment_label(a) for aid, a in engaged.items()}
            contacts = self._known_contacts(obs)
            plan = await asyncio.to_thread(
                self.strategist.plan, self.mission, to_allocate, self.scene, contacts, engaged_labels)
            allocation = dict(plan["allocation"])
            reasoning = plan.get("reasoning") or "Proposed task division."

            # Whole-team converge/intercept: once the target is known, send EVERY
            # un-engaged asset to it (deterministic — the order is unambiguous).
            target = self._converge_target(obs)
            if target is not None:
                for m in to_allocate:
                    allocation[m["id"]] = {"kind": "investigate", "contact_id": target}
                reasoning = f"Target {target} acquired — directing all assets to intercept it."

            allocation.update(engaged)   # engaged assets keep their task
            self.brief = plan["brief"]
            self.view.brief = plan["brief"]
            self.view.allocation = allocation
            self.view.last_proposal_t = obs.world_time
            await self.client.send_p2p(
                "all", "proposal",
                {"brief": plan["brief"], "allocation": allocation},
                reasoning=reasoning)
            note = " (re-dividing around engaged asset)" if engaged else ""
            await self.client.send_cot(f"Plan{note}: {reasoning}\n")
            logger.info("[%s] (leader) proposed allocation: %s%s", self.ctx.agent_id,
                        {k: assignment_label(v) for k, v in allocation.items()},
                        " | engaged=" + ",".join(engaged) if engaged else "")
        except Exception as exc:
            logger.warning("[%s] strategy failed (%s); using default sectors", self.ctx.agent_id, exc)
            self.view.allocation = default_allocation(self.view.live_member_ids(), self.scene.bounds)
        finally:
            self._thinking_strategy = False

    def _known_contacts(self, obs: Observation) -> list[dict[str, Any]]:
        out = {c.id: {"id": c.id, "label": c.label, "flagged": c.flagged} for c in obs.contacts}
        for cid, sc in self.view.contacts.items():
            out.setdefault(cid, {"id": cid, "label": sc.label, "flagged": sc.flagged})
        return list(out.values())

    # ── assignment adoption ──────────────────────────────────────────────────
    async def _refresh_assignment(self, obs: Observation) -> None:
        positions = {self.ctx.agent_id: (obs.lat, obs.lon)}
        for pid in self.view.live_peer_ids():
            p = self.view.peers[pid]
            positions[pid] = (p.lat, p.lon)
        member_ids = self.view.live_member_ids()

        if self._dynamic_assignment is not None:
            # A reactive override (e.g. following a discovered vessel) takes
            # precedence over the negotiated patrol allocation.
            new_assignment = self._dynamic_assignment
        else:
            # Provisional deterministic split until a proposal lands → instant, non-erratic start.
            allocation = self.view.allocation or default_allocation(member_ids, self.scene.bounds)
            allocation = deconflict(allocation, member_ids, positions, self.scene.bounds)
            new_assignment = allocation.get(self.ctx.agent_id)

        if new_assignment != self.assignment:
            had_proposal = self.view.brief is not None
            self.assignment = new_assignment
            self._assignment_label = assignment_label(new_assignment)
            # Rebuild only the baseline; an in-progress reaction (investigate /
            # report) is independent of the patrol assignment and must persist.
            self.baseline_tool = self._build_baseline(new_assignment, obs)
            await self.client.send_cot(f"Assignment: {self._assignment_label}\n")
            # Acknowledge the leader's proposal (visible coordination), unless we are leader.
            if had_proposal and not self._is_leader():
                await self.client.send_p2p(
                    "all", "ack", {"assignment": new_assignment},
                    reasoning=f"Acknowledged — taking {self._assignment_label}.")

    def _build_baseline(self, assignment: dict[str, Any] | None, obs: Observation) -> Tool | None:
        if not assignment:
            return None
        kind = (assignment.get("kind") or "").lower()
        spec: tuple[str, dict[str, Any]] | None = None
        if kind == "patrol_sector":
            spec = ("patrol_sector", {"sector": assignment.get("sector", "CENTER")})
        elif kind == "investigate":
            spec = ("investigate_contact", {"contact_id": assignment.get("contact_id")})
        elif kind == "escort":
            spec = ("escort_contact", {"contact_id": assignment.get("contact_id"),
                                       "standoff_m": assignment.get("standoff_m", 500),
                                       "bearing_deg": assignment.get("bearing_deg", 0)})
        elif kind == "visit_pois":
            spec = ("visit_pois", {"poi_ids": assignment.get("poi_ids", []),
                                   "rendezvous": assignment.get("rendezvous")})
        elif kind == "rendezvous":
            spec = ("rendezvous", {"poi_id": assignment.get("poi_id") or assignment.get("point")})
        elif kind == "go_to":
            spec = ("go_to", {"lat": assignment.get("lat"), "lon": assignment.get("lon")})
        elif kind == "hold":
            spec = ("hold_position", {"seconds": 60})
        try:
            if spec is not None:
                return self.registry.build(spec[0], spec[1], self.ctx)
        except ToolError as exc:
            logger.info("[%s] baseline build failed (%s); patrolling instead", self.ctx.agent_id, exc)
        # fallback: patrol the nearest sector so we still move sensibly
        return self._fallback_patrol(obs)

    def _fallback_patrol(self, obs: Observation) -> Tool | None:
        from maritime_swarm.ai_control.coordination import SECTORS, sector_center
        from maritime_swarm.ai_control.geo import haversine_km
        best = min(SECTORS, key=lambda s: haversine_km(obs.lat, obs.lon, *sector_center(self.scene.bounds, s)))
        try:
            return self.registry.build("patrol_sector", {"sector": best}, self.ctx)
        except ToolError:
            return None

    # ── reactive (tactician) ─────────────────────────────────────────────────
    def _already_handled(self, contact_id: str) -> bool:
        if contact_id in self._handled:
            return True
        sc = self.view.contacts.get(contact_id)
        if sc and sc.reported:
            return True
        # A live peer is already following this contact → don't pile on; the
        # peer's status/handoff told us. We re-cover the area instead.
        for pid in self.view.live_peer_ids():
            a = self.view.peers[pid].assignment
            if a and (a.get("kind") or "") == "escort" and a.get("contact_id") == contact_id:
                return True
        return False

    def _unhandled_suspicious(self, obs: Observation) -> bool:
        return any(c.is_suspicious and not self._already_handled(c.id) for c in obs.contacts)

    def _is_follow_mission(self) -> bool:
        return any(w in (self.mission or "").lower() for w in _FOLLOW_WORDS)

    def _mission_standoff_m(self) -> float:
        m = re.search(r"(\d{2,5})\s*m\b", (self.mission or "").lower())
        return float(m.group(1)) if m else 500.0

    async def _engage_escort(self, contact_id: str, standoff_m: float, reason: str) -> None:
        """Commit to following a contact at a standoff — the agent's standing task."""
        try:
            self.baseline_tool = self.registry.build(
                "escort_contact",
                {"contact_id": contact_id, "standoff_m": standoff_m, "bearing_deg": 180.0}, self.ctx)
            assignment = {"kind": "escort", "contact_id": contact_id,
                          "standoff_m": standoff_m, "bearing_deg": 180.0}
            self._dynamic_assignment = assignment
            self.assignment = assignment
            self._assignment_label = assignment_label(assignment)
            self.reactive_tool = None
            self._handled.add(contact_id)
            logger.info("[%s] engaging — following %s at %d m", self.ctx.agent_id, contact_id, int(standoff_m))
            await self.client.send_cot(reason + "\n")
            await self.client.send_p2p(
                "all", "handoff", {"assignment": assignment},
                reasoning=f"Engaging: following unreported vessel {contact_id} at {int(standoff_m)} m.")
        except ToolError as exc:
            logger.info("[%s] cannot escort %s (%s)", self.ctx.agent_id, contact_id, exc)
        finally:
            self._thinking_reactive = False

    def _maybe_react(self, obs: Observation) -> None:
        if self.reactive_tool is not None or self._thinking_reactive:
            return
        # Once committed to following a vessel, stay on it.
        if self._dynamic_assignment is not None:
            return
        # A directional team order ('go south') is obeyed as-is — don't get pulled
        # off course by passing contacts.
        if self.assignment and (self.assignment.get("kind") or "") == "go_to":
            return

        # Follow/shadow mission: a sensed unreported vessel IS the target — engage
        # it directly and deterministically (no fragile chase-to-identify, no
        # dependence on a second LLM call). The escort then closes to the standoff.
        if self._is_follow_mission():
            target = next((c for c in obs.contacts
                           if c.is_suspicious and not self._already_handled(c.id)), None)
            if target is not None:
                self._thinking_reactive = True
                asyncio.create_task(self._engage_escort(
                    target.id, self._mission_standoff_m(),
                    f"Found unreported vessel {target.id} — following at {int(self._mission_standoff_m())} m."))
                return

        pending = self._pending_report is not None
        # Don't keep reacting to contacts the team has already handled.
        if not pending and not self._unhandled_suspicious(obs):
            return
        now = time.monotonic()
        if not pending and (now - self._last_reactive_think) < REACTIVE_INTERVAL_S:
            return
        self._thinking_reactive = True
        asyncio.create_task(self._run_reactive(obs))

    async def _run_reactive(self, obs: Observation) -> None:
        focus = self._pending_report
        self._pending_report = None
        try:
            peers = [{"id": pid, "assignment_label": assignment_label(self.view.peers[pid].assignment)}
                     for pid in self.view.live_peer_ids()]
            d = await asyncio.to_thread(
                self.tactician.decide_reactive, obs, self.ctx, self.mission, self.brief,
                self._assignment_label, peers, focus)
            action = d.get("action")
            cid = d.get("contact_id")
            if action == "investigate" and cid:
                self.reactive_tool = self.registry.build("investigate_contact", {"contact_id": cid}, self.ctx)
                await self.client.send_cot((d.get("reasoning") or f"Investigating {cid}") + "\n")
            elif action == "report" and cid and cid not in self._handled:
                self.reactive_tool = self.registry.build(
                    "report_contact",
                    {"contact_id": cid, "classification": d.get("classification") or "SUSPICIOUS",
                     "rationale": d.get("rationale") or ""},
                    self.ctx)
                self._handled.add(cid)
                await self.client.send_cot((d.get("reasoning") or f"Reporting {cid}") + "\n")
            elif action == "escort" and cid and self._is_follow_mission():
                # Only commit to following when the mission actually calls for it
                # (guards against the model proposing escort on an unrelated order).
                standoff = d.get("standoff_m") or self._mission_standoff_m()
                await self._engage_escort(
                    cid, standoff, d.get("reasoning") or f"Following {cid} at {int(standoff)} m")
            # else: continue on baseline
        except ToolError as exc:
            logger.info("[%s] reactive build rejected (%s)", self.ctx.agent_id, exc)
        except Exception as exc:
            logger.warning("[%s] tactician error: %s", self.ctx.agent_id, exc)
        finally:
            self._last_reactive_think = time.monotonic()
            self._thinking_reactive = False

    # ── execution ──────────────────────────────────────────────────────────
    async def _execute(self, obs: Observation) -> None:
        active = self.reactive_tool or self.baseline_tool
        if active is None:
            return
        inv = active.step(obs, self.ctx)
        if inv.action is not None:
            self._current_task = inv.action.get("current_task", self._current_task)
            await self.client.send_action(inv.action)
        if inv.p2p is not None:
            self.view.ingest(self.ctx.agent_id, inv.p2p.get("msg_type", "status"), inv.p2p.get("content", {}))
            await self.client.send_p2p(
                inv.p2p.get("to", "all"), inv.p2p.get("msg_type", "status"),
                inv.p2p.get("content", {}), reasoning=inv.p2p.get("reasoning"))
        if inv.finished:
            if active is self.reactive_tool:
                # Finished investigating a contact → queue a focused "report it?" decision.
                if active.name == "investigate_contact" and inv.status.value == "done":
                    cid = getattr(active, "contact_id", None)
                    sc = self.view.contacts.get(cid) if cid else None
                    if sc is not None and not self._already_handled(cid):
                        self._pending_report = {"id": cid, "label": sc.label, "flagged": sc.flagged}
                self.reactive_tool = None  # resume the baseline task
            else:
                # If a follow/escort lost its contact, disengage and rejoin patrol
                # (the leader re-divides once it sees we're no longer engaged).
                if self._dynamic_assignment is not None and inv.status is ToolStatus.FAILED:
                    logger.info("[%s] lost escorted contact — disengaging.", self.ctx.agent_id)
                    asyncio.create_task(self.client.send_cot("Lost the contact — rejoining patrol.\n"))
                    self._dynamic_assignment = None
                    self.assignment = None
                self.baseline_tool = self._build_baseline(self.assignment, obs) if self.assignment else None
