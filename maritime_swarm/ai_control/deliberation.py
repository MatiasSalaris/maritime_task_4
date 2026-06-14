"""Decentralised deliberation protocol for agent-to-agent convergence."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from maritime_swarm.ai_control.coordination import SECTORS, deconflict
from maritime_swarm.ai_control.tools import Bounds

MAX_DELIBERATION_ROUNDS = 4
MIN_DELIBERATION_SECONDS = 6.0
MIN_DISCUSSION_ROUNDS = 2
DELIBERATION_MSG_KIND = "deliberation"
AREA_TOOLS = {"patrol_sector", "search_area"}
NARROW_SECTORS = set(SECTORS)
BROAD_SECTORS = {
    "WEST": {"NW", "SW"},
    "EAST": {"NE", "SE"},
    "NORTH": {"NW", "NE"},
    "SOUTH": {"SW", "SE"},
    "ALL": set(SECTORS),
}


def _sector_footprint(sector: Any) -> set[str]:
    value = str(sector or "").upper()
    if value in NARROW_SECTORS:
        return {value}
    return set(BROAD_SECTORS.get(value, set()))


@dataclass
class Proposal:
    """One agent's proposed next tool call inside a deliberation session."""

    agent_id: str
    tool: str
    args: dict[str, Any]
    rationale: str
    round: int


@dataclass
class DeliberationSession:
    """Local copy of a bounded-round deliberation session."""

    session_id: str
    trigger: str
    started_at: float
    max_rounds: int = MAX_DELIBERATION_ROUNDS
    round: int = 1
    proposals: dict[str, Proposal] = field(default_factory=dict)
    votes: dict[tuple[str, str], str] = field(default_factory=dict)
    objections: dict[tuple[str, str], str] = field(default_factory=dict)
    committed_plan: dict[str, dict[str, Any]] | None = None
    commit_reason: str | None = None

    def record_proposal(self, proposal: Proposal) -> None:
        existing = self.proposals.get(proposal.agent_id)
        if existing is None or proposal.round >= existing.round:
            self.proposals[proposal.agent_id] = proposal
            self.round = max(self.round, proposal.round)

    def record_vote(self, voter: str, target: str, vote: str, rationale: str, round_no: int) -> None:
        self.votes[(voter, target)] = vote
        if vote == "objection":
            self.objections[(voter, target)] = rationale
        self.round = max(self.round, round_no)

    def has_vote(self, voter: str, target: str) -> bool:
        return (voter, target) in self.votes

    def ack_count(self, target: str) -> int:
        return sum(1 for (_, voted_target), vote in self.votes.items() if voted_target == target and vote == "ack")

    def has_objection_to(self, target: str) -> bool:
        return any(voted_target == target for (_, voted_target) in self.objections)

    def live_members_with_proposals(self, live_ids: set[str]) -> set[str]:
        return {agent_id for agent_id in self.proposals if agent_id in live_ids}


def session_id_for(trigger: str, mission: str | None) -> str:
    """Build a stable short session id shared by agents seeing the same trigger."""

    raw = f"{trigger}|{(mission or '').strip()}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    safe_trigger = "".join(ch if ch.isalnum() else "_" for ch in trigger.lower()).strip("_") or "event"
    return f"delib-{safe_trigger}-{digest}"


def deliberation_payload(
    *,
    session: DeliberationSession,
    phase: str,
    text: str,
    agent_id: str,
    tool: str | None = None,
    args: dict[str, Any] | None = None,
    rationale: str = "",
    target: str | None = None,
) -> dict[str, Any]:
    """Create a content payload compatible with the existing P2P bus/UI."""

    payload: dict[str, Any] = {
        "text": text,
        "kind": DELIBERATION_MSG_KIND,
        "session_id": session.session_id,
        "trigger": session.trigger,
        "phase": phase,
        "round": session.round,
        "agent_id": agent_id,
        "rationale": rationale,
    }
    if tool:
        payload["tool"] = tool
        payload["args"] = args or {}
    if target:
        payload["target"] = target
    return payload


def parse_deliberation_message(content: dict[str, Any]) -> dict[str, Any] | None:
    """Return structured deliberation data from a P2P content dict, if present."""

    if not isinstance(content, dict) or content.get("kind") != DELIBERATION_MSG_KIND:
        return None
    session_id = str(content.get("session_id") or "").strip()
    phase = str(content.get("phase") or "").strip()
    if not session_id or not phase:
        return None
    return content


def proposals_conflict(left: Proposal, right: Proposal) -> bool:
    """Detect conflicts that should force objection/counterproposal."""

    if left.tool in AREA_TOOLS and right.tool in AREA_TOOLS:
        left_footprint = _sector_footprint(left.args.get("sector"))
        right_footprint = _sector_footprint(right.args.get("sector"))
        return bool(left_footprint and right_footprint and left_footprint & right_footprint)
    if left.tool == right.tool == "investigate_contact":
        return str(left.args.get("contact_id") or "") == str(right.args.get("contact_id") or "")
    return False


def build_commit_plan(
    session: DeliberationSession,
    live_ids: set[str],
    positions: dict[str, tuple[float, float]],
    bounds: Bounds,
) -> dict[str, dict[str, Any]]:
    """Return a converged per-agent plan with deterministic deconfliction."""

    plan: dict[str, dict[str, Any]] = {}
    for agent_id in sorted(live_ids):
        proposal = session.proposals.get(agent_id)
        if proposal is not None:
            plan[agent_id] = {"tool": proposal.tool, "args": dict(proposal.args)}

    sector_alloc: dict[str, dict[str, Any]] = {}
    area_agent_ids: set[str] = set()
    for agent_id, spec in plan.items():
        tool = spec.get("tool")
        args = spec.get("args") or {}
        if tool in AREA_TOOLS:
            area_agent_ids.add(agent_id)
            sector = str(args.get("sector") or "").upper()
            if sector in NARROW_SECTORS:
                sector_alloc[agent_id] = {"kind": "patrol_sector", "sector": sector}

    if area_agent_ids:
        resolved = deconflict(sector_alloc, sorted(area_agent_ids), positions, bounds)
        for agent_id, assignment in resolved.items():
            if (assignment.get("kind") or "") == "patrol_sector":
                original_tool = plan.get(agent_id, {}).get("tool") or "search_area"
                if original_tool not in AREA_TOOLS:
                    original_tool = "search_area"
                args = dict(plan.get(agent_id, {}).get("args") or {})
                args["sector"] = assignment.get("sector", args.get("sector", "AUTO"))
                plan[agent_id] = {"tool": original_tool, "args": args}

    return plan
