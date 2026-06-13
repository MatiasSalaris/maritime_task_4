from __future__ import annotations
import math
from models.agent import Position

# Earth radius in km
_R = 6371.0


def move(pos: Position, heading_deg: float, speed_kn: float, dt_s: float) -> Position:
    """Return new position after moving at given heading/speed for dt_s seconds."""
    speed_ms = speed_kn * 0.514444
    dist_m = speed_ms * dt_s

    h = math.radians(heading_deg)
    lat_r = math.radians(pos.lat)

    dlat = (dist_m / 111_000) * math.cos(h)
    dlon = (dist_m / (111_000 * math.cos(lat_r))) * math.sin(h)

    return Position(lat=pos.lat + dlat, lon=pos.lon + dlon)


def distance_km(a: Position, b: Position) -> float:
    dlat = math.radians(b.lat - a.lat)
    dlon = math.radians(b.lon - a.lon)
    x = math.sin(dlat / 2) ** 2 + (
        math.cos(math.radians(a.lat)) * math.cos(math.radians(b.lat)) * math.sin(dlon / 2) ** 2
    )
    return _R * 2 * math.asin(math.sqrt(x))


def bearing_to(a: Position, b: Position) -> float:
    """Return compass bearing (0-360) from a to b."""
    lat1, lon1 = math.radians(a.lat), math.radians(a.lon)
    lat2, lon2 = math.radians(b.lat), math.radians(b.lon)
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360
