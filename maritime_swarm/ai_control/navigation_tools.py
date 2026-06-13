"""Concrete navigation tools and the default tool registry.

Each tool turns a high-level command into per-tick world-model actions by
steering the agent (setting ``heading`` + ``speed_kn``) toward a target and
reporting ``DONE`` when it arrives.
"""

from __future__ import annotations

from typing import Any

from maritime_swarm.ai_control.geo import bearing_deg, haversine_km
from maritime_swarm.ai_control.observation import Observation
from maritime_swarm.ai_control.tools import (
    Tool,
    ToolContext,
    ToolInvocation,
    ToolRegistry,
    ToolStatus,
    require_number,
    require_str,
)


def _steer_action(obs: Observation, lat: float, lon: float, ctx: ToolContext, task: str) -> dict[str, Any]:
    """Build a world action that heads the agent toward (lat, lon)."""
    return {
        "heading": bearing_deg(obs.lat, obs.lon, lat, lon),
        "speed_kn": ctx.cruise_speed_kn,
        "planned_path": [{"lat": lat, "lon": lon}],
        "current_task": task,
    }


def _stop_action(task: str) -> dict[str, Any]:
    return {"speed_kn": 0.0, "planned_path": [], "current_task": task}


class GoToTool(Tool):
    """Transit to a geographic waypoint and stop on arrival."""

    name = "go_to"
    description = "Transit to a geographic waypoint (latitude, longitude) and hold there on arrival."
    parameters = {
        "lat": {"type": "number", "description": "target latitude in decimal degrees"},
        "lon": {"type": "number", "description": "target longitude in decimal degrees"},
    }

    def __init__(self, lat: float, lon: float) -> None:
        self.lat = lat
        self.lon = lon

    @classmethod
    def build(cls, args: dict[str, Any], ctx: ToolContext) -> "GoToTool":
        lat = require_number(args, "lat")
        lon = require_number(args, "lon")
        if ctx.bounds is not None:
            lat, lon = ctx.bounds.clamp_point(lat, lon)
        return cls(lat, lon)

    def step(self, obs: Observation, ctx: ToolContext) -> ToolInvocation:
        dist = haversine_km(obs.lat, obs.lon, self.lat, self.lon)
        if dist <= ctx.arrival_km:
            return ToolInvocation(
                _stop_action(f"On station @ {self.lat:.3f}, {self.lon:.3f}"),
                ToolStatus.DONE,
                "arrived",
            )
        task = f"Transit to {self.lat:.3f}, {self.lon:.3f} ({dist:.1f} km)"
        return ToolInvocation(_steer_action(obs, self.lat, self.lon, ctx, task), ToolStatus.RUNNING, f"{dist:.2f} km to go")

    def describe(self) -> str:
        return f"go_to({self.lat:.4f}, {self.lon:.4f})"


class InvestigateContactTool(Tool):
    """Close in on a sensed contact to identify it."""

    name = "investigate_contact"
    description = (
        "Approach a contact currently in sensor range, by its id, to identify it. "
        "Completes when the contact is reached; fails if the contact is not (or no longer) sensed."
    )
    parameters = {
        "contact_id": {
            "type": "string",
            "description": "id of a contact from the current contacts-in-range list (e.g. 'c003')",
        },
    }

    def __init__(self, contact_id: str) -> None:
        self.contact_id = contact_id
        self._last_pos: tuple[float, float] | None = None

    @classmethod
    def build(cls, args: dict[str, Any], ctx: ToolContext) -> "InvestigateContactTool":
        return cls(require_str(args, "contact_id"))

    def step(self, obs: Observation, ctx: ToolContext) -> ToolInvocation:
        target = obs.contact(self.contact_id)
        if target is not None:
            self._last_pos = (target.lat, target.lon)
        if self._last_pos is None:
            return ToolInvocation(None, ToolStatus.FAILED, f"contact {self.contact_id} not in range")

        tlat, tlon = self._last_pos
        dist = haversine_km(obs.lat, obs.lon, tlat, tlon)
        if dist <= ctx.arrival_km:
            return ToolInvocation(
                _stop_action(f"Identifying contact {self.contact_id}"),
                ToolStatus.DONE,
                "reached contact",
            )
        task = f"Intercepting {self.contact_id} ({dist:.1f} km)"
        return ToolInvocation(_steer_action(obs, tlat, tlon, ctx, task), ToolStatus.RUNNING, f"{dist:.2f} km to contact")

    def describe(self) -> str:
        return f"investigate_contact({self.contact_id})"


class HoldPositionTool(Tool):
    """Stop and hold station for a short period to observe."""

    name = "hold_position"
    description = "Stop and hold the current position for a number of seconds to observe the area."
    parameters = {
        "seconds": {
            "type": "number",
            "description": "how long to hold station, in seconds (default 20)",
            "required": False,
        },
    }

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self._start_t: float | None = None

    @classmethod
    def build(cls, args: dict[str, Any], ctx: ToolContext) -> "HoldPositionTool":
        seconds = 20.0
        if args.get("seconds") is not None:
            seconds = require_number(args, "seconds")
        seconds = max(5.0, min(120.0, seconds))
        return cls(seconds)

    def step(self, obs: Observation, ctx: ToolContext) -> ToolInvocation:
        if self._start_t is None:
            self._start_t = obs.world_time
        elapsed = obs.world_time - self._start_t
        if elapsed >= self.seconds:
            return ToolInvocation(_stop_action("Hold complete"), ToolStatus.DONE, "hold elapsed")
        remaining = int(self.seconds - elapsed)
        return ToolInvocation(_stop_action(f"Holding station ({remaining}s)"), ToolStatus.RUNNING, f"{remaining}s left")

    def describe(self) -> str:
        return f"hold_position({self.seconds:.0f}s)"


def default_registry() -> ToolRegistry:
    """The standard maritime patrol toolset."""
    registry = ToolRegistry()
    registry.register(GoToTool)
    registry.register(InvestigateContactTool)
    registry.register(HoldPositionTool)
    return registry
