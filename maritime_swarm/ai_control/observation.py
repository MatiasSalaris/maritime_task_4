"""Typed view of a world-model observation.

The world model pushes ``{"type": "observation", "payload": {...}}`` to a
connected agent every tick. The payload matches the backend ``Observation``
model. We parse it into small dataclasses so tools and the brain can work with
attributes instead of raw dicts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SensedContact:
    """A contact currently within the agent's sensor range."""

    id: str
    lat: float
    lon: float
    label: str = "UNKNOWN"
    flagged: bool = False
    mmsi: str | None = None
    heading: float = 0.0
    speed_kn: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_suspicious(self) -> bool:
        """Unknown or flagged contacts are the ones worth investigating."""
        return self.flagged or self.label.upper() == "UNKNOWN"

    @property
    def is_buoy(self) -> bool:
        """Mission target for buoy-search scenarios."""
        return self.label.upper() == "BUOY"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SensedContact":
        pos = d.get("position") or {}
        return cls(
            id=str(d.get("id", "")),
            lat=float(pos.get("lat", 0.0)),
            lon=float(pos.get("lon", 0.0)),
            label=str(d.get("label", "UNKNOWN")),
            flagged=bool(d.get("flagged", False)),
            mmsi=d.get("mmsi"),
            heading=float(d.get("heading", 0.0) or 0.0),
            speed_kn=float(d.get("speed_kn", 0.0) or 0.0),
            raw=d,
        )


@dataclass
class Observation:
    """What a single agent senses on one tick."""

    agent_id: str
    lat: float
    lon: float
    heading: float
    speed_kn: float
    contacts: list[SensedContact] = field(default_factory=list)
    inbox: list[dict[str, Any]] = field(default_factory=list)
    world_time: float = 0.0
    mission: str | None = None
    mission_status: str = "idle"
    mission_result: dict[str, Any] | None = None
    aor: dict[str, Any] | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "Observation":
        pos = payload.get("position") or {}
        contacts = [SensedContact.from_dict(c) for c in payload.get("contacts_in_range", [])]
        return cls(
            agent_id=str(payload.get("agent_id", "")),
            lat=float(pos.get("lat", 0.0)),
            lon=float(pos.get("lon", 0.0)),
            heading=float(payload.get("heading", 0.0) or 0.0),
            speed_kn=float(payload.get("speed_kn", 0.0) or 0.0),
            contacts=contacts,
            inbox=list(payload.get("messages_inbox", [])),
            world_time=float(payload.get("world_time", 0.0) or 0.0),
            mission=payload.get("mission"),
            mission_status=str(payload.get("mission_status") or "idle"),
            mission_result=payload.get("mission_result"),
            aor=payload.get("aor"),
        )

    def contact(self, contact_id: str) -> SensedContact | None:
        for c in self.contacts:
            if c.id == contact_id:
                return c
        return None
