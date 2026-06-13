"""Deterministic scoring and assignment utilities."""

from __future__ import annotations

import math
from typing import Any

MAX_OPERATIONAL_DISTANCE = 140.0


def calculate_utility(
    pos: tuple[float, float],
    battery: float,
    sensor_quality: float,
    target_pos: tuple[float, float],
) -> tuple[float, dict[str, float]]:
    """Return deterministic utility and its explainable score components."""
    distance = math.dist(pos, target_pos)
    distance_score = max(0.0, 1.0 - (distance / MAX_OPERATIONAL_DISTANCE))
    battery_score = max(0.0, min(1.0, battery / 100.0))
    sensor_score = max(0.0, min(1.0, sensor_quality))
    utility = 0.5 * distance_score + 0.3 * battery_score + 0.2 * sensor_score
    return round(utility, 3), {
        "distance": distance,
        "normalized_distance_score": distance_score,
        "normalized_battery": battery_score,
        "sensor_quality": sensor_score,
    }


def select_winner(bids: dict[str, dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    """Return the highest-utility bid, using agent id as a stable tie-breaker."""
    if not bids:
        raise ValueError("cannot assign task without bids")
    return sorted(bids.items(), key=lambda item: (-item[1]["utility"], item[0]))[0]


def format_bids(bids: dict[str, dict[str, Any]]) -> str:
    """Format a bid table for readable demo logs."""
    return "{" + ", ".join(f"{k}: {v['utility']:.3f}" for k, v in sorted(bids.items())) + "}"
