"""Each agent's local view of the swarm — its shared situational picture.

This is built **only** from peer-to-peer messages received over the world
model's bus (status / proposal / ack / objection / handoff), never from a
god-view. So it embodies the brief's requirements directly:

- a *shared situational picture* reconciled from what peers report,
- *peer awareness* without a central node,
- *failure honesty*: a peer whose status has gone stale is treated as silent.

Inter-agent state lives nowhere central — every brain keeps its own SwarmView
and they converge by exchanging messages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# How long since a peer's last status before we consider it silent (seconds of
# world time). Tunable; status is broadcast every few seconds.
PEER_SILENT_TTL = 9.0


@dataclass
class PeerInfo:
    agent_id: str
    name: str | None = None
    agent_type: str | None = None
    lat: float = 0.0
    lon: float = 0.0
    heading: float = 0.0
    speed_kn: float = 0.0
    task: str | None = None
    assignment: dict[str, Any] | None = None
    updated_t: float = 0.0


@dataclass
class SharedContact:
    """A contact in the common picture, merged across reporters."""

    id: str
    lat: float
    lon: float
    label: str = "UNKNOWN"
    flagged: bool = False
    classification: str | None = None        # agreed/assessed class, if any
    reported: bool = False                   # has someone reported it?
    reporters: set[str] = field(default_factory=set)
    updated_t: float = 0.0


class SwarmView:
    """One agent's reconciled picture of peers, the shared contacts and the plan."""

    def __init__(self, self_id: str) -> None:
        self.self_id = self_id
        self.peers: dict[str, PeerInfo] = {}
        self.contacts: dict[str, SharedContact] = {}
        self.brief: dict[str, Any] | None = None          # shared mission interpretation
        self.allocation: dict[str, dict[str, Any]] = {}   # agent_id -> assignment
        self.last_proposal_t: float = 0.0
        self.now: float = 0.0

    # ── time / liveness ───────────────────────────────────────────────────
    def tick(self, world_time: float) -> None:
        self.now = world_time

    def live_peer_ids(self) -> list[str]:
        return [p.agent_id for p in self.peers.values()
                if (self.now - p.updated_t) <= PEER_SILENT_TTL]

    def silent_peer_ids(self) -> list[str]:
        return [p.agent_id for p in self.peers.values()
                if (self.now - p.updated_t) > PEER_SILENT_TTL]

    def all_member_ids(self) -> list[str]:
        """Self + every peer we have ever heard from, sorted (stable order)."""
        return sorted({self.self_id, *self.peers.keys()})

    def live_member_ids(self) -> list[str]:
        """Self + non-silent peers, sorted."""
        return sorted({self.self_id, *self.live_peer_ids()})

    # ── ingest peer messages (content dicts from P2PMessage) ───────────────
    def ingest(self, from_agent: str, msg_type: str, content: dict[str, Any]) -> None:
        if not from_agent or from_agent == self.self_id:
            return
        if msg_type == "status":
            self._ingest_status(from_agent, content)
        elif msg_type == "proposal":
            self._ingest_proposal(content)
        # ack / objection / handoff update the allocation if they carry one
        if msg_type in ("ack", "objection", "handoff"):
            self._ingest_allocation_hint(from_agent, msg_type, content)
        # any message may carry shared-picture contact updates (status, report…)
        for c in content.get("contacts", []) or []:
            self._merge_contact(from_agent, c)

    def _ingest_status(self, from_agent: str, content: dict[str, Any]) -> None:
        pos = content.get("pos") or {}
        peer = self.peers.get(from_agent) or PeerInfo(agent_id=from_agent)
        peer.name = content.get("name", peer.name)
        peer.agent_type = content.get("type", peer.agent_type)
        peer.lat = float(pos.get("lat", peer.lat))
        peer.lon = float(pos.get("lon", peer.lon))
        peer.heading = float(content.get("heading", peer.heading))
        peer.speed_kn = float(content.get("speed_kn", peer.speed_kn))
        peer.task = content.get("task", peer.task)
        peer.assignment = content.get("assignment", peer.assignment)
        peer.updated_t = self.now
        self.peers[from_agent] = peer

    def observe(self, contacts: list[Any]) -> None:
        """Merge this agent's own sensed contacts into the shared picture, so a
        contact it has identified remains reportable even after it leaves range."""
        for c in contacts:
            self._merge_contact(self.self_id, {
                "id": c.id, "lat": c.lat, "lon": c.lon, "label": c.label, "flagged": c.flagged,
            })

    def _merge_contact(self, reporter: str, c: dict[str, Any]) -> None:
        cid = str(c.get("id", "")).strip()
        if not cid:
            return
        sc = self.contacts.get(cid)
        if sc is None:
            sc = SharedContact(id=cid, lat=float(c.get("lat", 0.0)), lon=float(c.get("lon", 0.0)))
            self.contacts[cid] = sc
        sc.lat = float(c.get("lat", sc.lat))
        sc.lon = float(c.get("lon", sc.lon))
        sc.label = c.get("label", sc.label)
        sc.flagged = bool(c.get("flagged", sc.flagged))
        if c.get("classification"):
            sc.classification = c["classification"]
        if c.get("reported"):
            sc.reported = True
        sc.reporters.add(reporter)
        sc.updated_t = self.now

    def _ingest_proposal(self, content: dict[str, Any]) -> None:
        brief = content.get("brief")
        alloc = content.get("allocation")
        if isinstance(brief, dict):
            self.brief = brief
        if isinstance(alloc, dict):
            # normalise: agent_id -> assignment dict
            self.allocation = {k: v for k, v in alloc.items() if isinstance(v, dict)}
            self.last_proposal_t = self.now

    def _ingest_allocation_hint(self, from_agent: str, msg_type: str, content: dict[str, Any]) -> None:
        assignment = content.get("assignment")
        if isinstance(assignment, dict):
            # a peer asserting/contesting its own assignment
            self.allocation[from_agent] = assignment

    # ── queries ────────────────────────────────────────────────────────────
    def my_assignment(self) -> dict[str, Any] | None:
        return self.allocation.get(self.self_id)

    def record_self_status(self, peer: PeerInfo) -> None:
        """Keep our own latest broadcast so prompts can show the full roster."""
        self.peers.setdefault(self.self_id, peer)
