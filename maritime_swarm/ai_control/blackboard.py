"""Each agent's local view of the swarm — its shared situational picture.

Built ONLY from peer-to-peer traffic over the world model's bus:
  - `status` heartbeats give peers' positions, current task and sensed contacts;
  - natural-language coordination messages (proposal / ack / objection / handoff
    / report) are kept as a short transcript the agent's LLM reads and answers.

Nothing lives in a central place — every agent keeps its own SwarmView and they
converge by exchanging messages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

PEER_SILENT_TTL = 12.0      # seconds of world time before a peer is "silent"
_MAX_MESSAGES = 12          # recent coordination messages kept for context


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
    updated_t: float = 0.0


@dataclass
class SharedContact:
    id: str
    lat: float
    lon: float
    label: str = "UNKNOWN"
    flagged: bool = False
    classification: str | None = None
    reported: bool = False
    reporters: set[str] = field(default_factory=set)
    updated_t: float = 0.0


@dataclass
class Msg:
    sender: str
    msg_type: str
    text: str
    t: float


class SwarmView:
    def __init__(self, self_id: str) -> None:
        self.self_id = self_id
        self.peers: dict[str, PeerInfo] = {}
        self.contacts: dict[str, SharedContact] = {}
        self.messages: list[Msg] = []
        self.now: float = 0.0

    def tick(self, world_time: float) -> None:
        self.now = world_time

    # ── liveness ───────────────────────────────────────────────────────────
    def live_peer_ids(self) -> list[str]:
        return [p.agent_id for p in self.peers.values() if (self.now - p.updated_t) <= PEER_SILENT_TTL]

    def silent_peer_ids(self) -> list[str]:
        return [p.agent_id for p in self.peers.values() if (self.now - p.updated_t) > PEER_SILENT_TTL]

    # ── ingest peer traffic ──────────────────────────────────────────────────
    def ingest(self, from_agent: str, msg_type: str, content: dict[str, Any], reasoning: str | None = None) -> None:
        if not from_agent or from_agent == self.self_id:
            return
        if msg_type == "status":
            self._ingest_status(from_agent, content)
        else:
            text = (reasoning or content.get("text") or "").strip()
            if text:
                self.messages.append(Msg(from_agent, msg_type, text, self.now))
                self.messages = self.messages[-_MAX_MESSAGES:]
        for c in content.get("contacts", []) or []:
            self._merge_contact(from_agent, c)

    def observe(self, contacts: list[Any]) -> None:
        """Merge our own sensed contacts so the picture (and reports) survive range loss."""
        for c in contacts:
            self._merge_contact(self.self_id, {
                "id": c.id, "lat": c.lat, "lon": c.lon, "label": c.label, "flagged": c.flagged})

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
        peer.updated_t = self.now
        self.peers[from_agent] = peer

    def _merge_contact(self, reporter: str, c: dict[str, Any]) -> None:
        cid = str(c.get("id", "")).strip()
        if not cid:
            return
        sc = self.contacts.get(cid) or SharedContact(id=cid, lat=float(c.get("lat", 0.0)), lon=float(c.get("lon", 0.0)))
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
        self.contacts[cid] = sc

    def recent_messages(self, n: int = 8) -> list[Msg]:
        return self.messages[-n:]
