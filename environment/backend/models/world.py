from __future__ import annotations
from typing import Optional
from pydantic import BaseModel
from models.agent import AgentState, Position


class Contact(BaseModel):
    id: str
    position: Position
    heading: float = 0.0
    speed_kn: float = 0.0
    label: str = "UNKNOWN"       # AIS_COMMERCIAL | AIS_FISHING | UNKNOWN | FLAGGED
    mmsi: Optional[str] = None
    flagged: bool = False


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
