from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel
from models.agent import AgentState, Position


class ContactStatus(str, Enum):
    ACTIVE  = "active"    # in ≥1 agent sensor range right now
    GHOST   = "ghost"     # was detected, now out of range
    UNKNOWN = "unknown"   # never detected (visible only in god mode)


class Contact(BaseModel):
    id: str
    position: Position
    heading: float = 0.0
    speed_kn: float = 0.0
    label: str = "UNKNOWN"       # AIS_COMMERCIAL | AIS_FISHING | UNKNOWN | FLAGGED
    mmsi: Optional[str] = None
    flagged: bool = False
    status: ContactStatus = ContactStatus.UNKNOWN
    nato_id: Optional[str] = None
    first_seen: Optional[float] = None
    last_seen: Optional[float] = None
    last_known_position: Optional[Position] = None  # ghost position
    detecting_agents: list[str] = []


class POI(BaseModel):
    id: str
    position: Position
    label: str
    visited: bool = False


class Geofence(BaseModel):
    id: str
    type: str                    # patrol_area | exclusion_zone
    coordinates: list[Position]  # polygon vertices


class WorldState(BaseModel):
    time: float
    agents: list[AgentState]
    contacts: list[Contact]
    pois: list[POI]
    geofences: list[Geofence]
    messages_in_flight: list[dict] = []
    message_log: list[dict] = []
    mission: Optional[str] = None
    mission_status: str = "idle"          # idle | active | completed
    mission_result: Optional[dict] = None
    doctrine: Optional[str] = None   # NATO phase code: PHASE0..PHASE3 or MSO
    aor: Optional[dict] = None       # GeoJSON Polygon for operating area
    sensor_footprints: dict[str, list] = {}   # agent_id → [[lon,lat],...] polygon
    detection_events: list[dict] = []          # cleared each tick after broadcast
