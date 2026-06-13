"""Navigation helpers for local obstacle handling."""

from __future__ import annotations

import math


def avoidance_waypoint(
    pos: tuple[float, float],
    obstacle_pos: tuple[float, float],
    target_pos: tuple[float, float],
    clearance: float = 15.0,
) -> tuple[float, float]:
    """Return a deterministic lateral waypoint around an obstacle."""
    route_x = target_pos[0] - pos[0]
    route_y = target_pos[1] - pos[1]
    length = math.hypot(route_x, route_y) or 1.0
    normal_x = -route_y / length
    normal_y = route_x / length
    return (
        round(obstacle_pos[0] + normal_x * clearance, 1),
        round(obstacle_pos[1] + normal_y * clearance, 1),
    )
