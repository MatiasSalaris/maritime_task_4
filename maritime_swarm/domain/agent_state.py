"""Agent state containers and state-machine values."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentMode(str, Enum):
    """Lifecycle mode for an autonomous maritime asset."""

    IDLE = "IDLE"
    EVALUATING = "EVALUATING"
    EXECUTING = "EXECUTING"


@dataclass
class AgentState:
    """Three-tier state: physical, cognitive, and distributed."""

    state: AgentMode = AgentMode.IDLE
    active_task: str | None = None
    local_event_log: list[dict[str, Any]] = field(default_factory=list)
    physical_state: dict[str, Any] = field(default_factory=dict)
    cognitive_state: dict[str, Any] = field(default_factory=dict)
    distributed_state: dict[str, Any] = field(default_factory=dict)


def build_agent_state(
    pos: tuple[float, float],
    battery: float,
    sensor_quality: float,
) -> AgentState:
    """Create the initial three-tier state for one agent."""
    return AgentState(
        physical_state={
            "pos": pos,
            "battery": battery,
            "sensor_quality": sensor_quality,
            "raw_contacts": [],
        },
        cognitive_state={
            "local_beliefs": {},
            "local_intent": "awaiting operator mission intent",
            "decision_traces": [],
        },
        distributed_state={
            "mission_intent": None,
            "shared_contacts": {},
            "global_tasks": {},
        },
    )
