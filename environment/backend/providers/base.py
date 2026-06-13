from __future__ import annotations
from abc import ABC, abstractmethod
from models.agent import Observation
from models.messages import P2PMessage
from models.world import WorldState


class AbstractPlatformProvider(ABC):
    """
    The only interface the engine talks to.
    Swap SimulatedPlatformProvider for HardwarePlatformProvider without touching
    anything above this layer.
    """

    @abstractmethod
    async def get_observation(
        self, agent_id: str, inbox: list[P2PMessage]
    ) -> Observation | None:
        """Return what agent_id can currently sense, plus its P2P inbox."""
        ...

    @abstractmethod
    async def apply_action(self, agent_id: str, action: dict) -> None:
        """Apply a movement / task action from an LLM agent."""
        ...

    @abstractmethod
    async def get_world_state(self) -> WorldState:
        """Return the authoritative world snapshot for the frontend."""
        ...

    @abstractmethod
    async def set_mission(self, mission: str) -> None:
        """Propagate a new (or changed) mission intent."""
        ...

    async def complete_mission(self, result: dict) -> None:
        """Mark the current mission complete with a structured result."""
        ...

    async def set_contact_position(self, contact_id: str, lat: float, lon: float) -> bool:
        """Move a simulated/contact target. Return False if the contact does not exist."""
        return False

    @abstractmethod
    async def set_agent_connected(self, agent_id: str, connected: bool) -> None:
        """Mark whether an LLM agent WS is active."""
        ...

    @abstractmethod
    async def update_agent_cot(self, agent_id: str, chunk: str) -> None:
        """Append a CoT chunk to the agent's visible thought text."""
        ...

    async def reset(self) -> None:
        """Clear all agent path history, CoT, tasks, and mission state."""

    async def set_doctrine(self, code: str) -> None:
        """Set NATO doctrine/ROE profile."""

    async def set_aor(self, geojson: dict | None) -> None:
        """Set operating area as GeoJSON Polygon (None = clear)."""

    async def tick(self, dt: float) -> None:
        """Advance sim time by dt seconds. No-op for hardware (time is real)."""
