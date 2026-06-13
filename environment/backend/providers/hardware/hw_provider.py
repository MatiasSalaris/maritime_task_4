from __future__ import annotations
"""
Hardware provider stub.

Replace the body of each method with calls to your real AIS feed,
MAVLink telemetry, or sensor API.  The engine, WebSocket handlers,
and frontend are completely unaware of this swap.

Set PROVIDER=hardware in the environment to activate this provider.
"""
import time
from models.agent import Observation
from models.messages import P2PMessage
from models.world import WorldState, Contact, POI, Geofence
from models.agent import AgentState, AgentType, Position
from providers.base import AbstractPlatformProvider


class HardwarePlatformProvider(AbstractPlatformProvider):

    def __init__(self) -> None:
        # TODO: initialise hardware connections here
        self._agents: list[AgentState] = []
        self._mission: str | None = None
        self._mission_status: str = "idle"
        self._mission_result: dict | None = None

    async def tick(self, dt: float) -> None:
        # Hardware time is real — poll sensors here if needed
        pass

    async def get_observation(
        self, agent_id: str, inbox: list[P2PMessage]
    ) -> Observation | None:
        # TODO: query real telemetry for agent_id
        raise NotImplementedError("HardwarePlatformProvider.get_observation")

    async def apply_action(self, agent_id: str, action: dict) -> None:
        # TODO: send command to real platform
        raise NotImplementedError("HardwarePlatformProvider.apply_action")

    async def get_world_state(self) -> WorldState:
        # TODO: aggregate real telemetry into WorldState
        raise NotImplementedError("HardwarePlatformProvider.get_world_state")

    async def set_mission(self, mission: str) -> None:
        self._mission = mission
        self._mission_status = "active" if mission.strip() else "idle"
        self._mission_result = None

    async def complete_mission(self, result: dict) -> None:
        self._mission_status = "completed"
        self._mission_result = result

    async def set_contact_position(self, contact_id: str, lat: float, lon: float) -> bool:
        return False

    async def set_agent_connected(self, agent_id: str, connected: bool) -> None:
        pass

    async def update_agent_cot(self, agent_id: str, chunk: str) -> None:
        pass
