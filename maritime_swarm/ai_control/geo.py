"""Self-contained geographic helpers for the AI control layer.

These intentionally mirror the maths used by the world model's physics
(``environment/backend/providers/simulation/physics.py``) so that a heading we
compute here drives the agent toward the intended point. The AI layer keeps its
own copy rather than importing the backend, preserving the separation between
the brain and the world model.
"""

from __future__ import annotations

import math

_R_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in kilometres."""
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return _R_KM * 2 * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compass bearing (0-360, 0 = north) from point 1 to point 2.

    Matches ``physics.bearing_to`` in the backend so the resulting heading,
    fed back as an action, moves the agent toward the target.
    """
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def destination(lat: float, lon: float, bearing_deg: float, dist_km: float) -> tuple[float, float]:
    """Point reached by travelling ``dist_km`` from (lat,lon) on a compass bearing."""
    b = math.radians(bearing_deg)
    dlat = (dist_km / 111.32) * math.cos(b)
    cos_lat = math.cos(math.radians(lat)) or 1e-6
    dlon = (dist_km / (111.32 * cos_lat)) * math.sin(b)
    return (lat + dlat, lon + dlon)
