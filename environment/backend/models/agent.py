from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel


class AgentType(str, Enum):
    USV = "USV"
    UAV = "UAV"


class AgentStatus(str, Enum):
    OPERATIONAL = "operational"
    DEGRADED = "degraded"
    SILENT = "silent"


class Position(BaseModel):
    lat: float
    lon: float


class AgentState(BaseModel):
    id: str
    name: str
    type: AgentType = AgentType.USV
    position: Position
    heading: float = 0.0        # degrees 0-360, 0 = north
    speed_kn: float = 8.0
    status: AgentStatus = AgentStatus.OPERATIONAL
    current_task: Optional[str] = None
    path_history: list[Position] = []
    planned_path: list[Position] = []
    connected: bool = False     # whether an LLM agent is connected via WS
    cot_text: str = ""          # latest chain-of-thought chunk
    decision_log: list[dict] = []  # recent visible reasoning entries
    altitude_m: float = 0.0        # 0 for USV, ~1000 for UAV
    sensor_range_km: float = 12.0  # set per type in sim_provider


class Action(BaseModel):
    heading: Optional[float] = None
    speed_kn: Optional[float] = None
    planned_path: Optional[list[Position]] = None
    current_task: Optional[str] = None
    warp_to: Optional[Position] = None   # direct position set (demo / testing)


class Observation(BaseModel):
    agent_id: str
    position: Position
    heading: float
    speed_kn: float
    contacts_in_range: list[dict] = []
    messages_inbox: list[dict] = []
    world_time: float
    mission: Optional[str] = None
    mission_status: str = "idle"
    mission_result: Optional[dict] = None
    aor: Optional[dict] = None
