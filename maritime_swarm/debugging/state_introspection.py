"""State capture helpers for richer debugging snapshots."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, TYPE_CHECKING


if TYPE_CHECKING:  # pragma: no cover - used only for typing
    from maritime_swarm.agent_runtime.maritime_agent import MaritimeAgent


def _simplify_event(event: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of an event with rounded timestamps."""

    simplified = {**event}
    timestamp = simplified.get("timestamp")
    if isinstance(timestamp, (int, float)):
        simplified["timestamp"] = round(float(timestamp), 4)
    return simplified


def capture_agent_state(
    agent: "MaritimeAgent",
    *,
    event: dict[str, Any] | None = None,
    limit_events: int = 10,
    limit_traces: int = 5,
) -> dict[str, Any]:
    """Create a JSON-serialisable snapshot of an agent's three-tier state."""

    physical_state = deepcopy(agent.state.physical_state)
    cognitive_state = deepcopy(agent.state.cognitive_state)
    distributed_state = deepcopy(agent.state.distributed_state)

    decision_traces = list(cognitive_state.pop("decision_traces", []))
    if limit_traces:
        decision_traces = decision_traces[-limit_traces:]

    recent_events = [
        _simplify_event(item)
        for item in agent.state.local_event_log[-limit_events:]
    ]

    snapshot: dict[str, Any] = {
        "agent_id": agent.id,
        "mode": agent.state.state.value,
        "active_task": agent.state.active_task,
        "physical_state": physical_state,
        "cognitive_state": cognitive_state,
        "decision_traces": decision_traces,
        "distributed_state": distributed_state,
        "recent_events": recent_events,
        "battery_level": physical_state.get("battery"),
    }

    if event is not None:
        snapshot["trigger_event"] = _simplify_event(event)

    return snapshot
