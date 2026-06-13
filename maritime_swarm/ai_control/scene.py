"""Static scenario context pulled once from the world model.

This is the *area definition* an operator would brief the assets with: the
operating-area bounds and named points of interest. It is fetched once from
``GET /api/state`` at startup. We deliberately do **not** feed the full live
contact list from that endpoint into the LLM — agents only reason about what
their own sensors detect (fog of war). The scene is just the map.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from maritime_swarm.ai_control.tools import Bounds


@dataclass
class POI:
    id: str
    label: str
    lat: float
    lon: float


@dataclass
class Scene:
    bounds: Bounds
    pois: list[POI] = field(default_factory=list)

    @classmethod
    def from_world_state(cls, state: dict[str, Any]) -> "Scene":
        bounds = _bounds_from_geofences(state.get("geofences", []))
        pois = [
            POI(
                id=str(p.get("id", "")),
                label=str(p.get("label", "")),
                lat=float((p.get("position") or {}).get("lat", 0.0)),
                lon=float((p.get("position") or {}).get("lon", 0.0)),
            )
            for p in state.get("pois", [])
        ]
        return cls(bounds=bounds, pois=pois)


# Fallback bounds (Strait of Sicily demo area) if no patrol geofence is present.
_DEFAULT_BOUNDS = Bounds(lat_min=37.42, lat_max=37.60, lon_min=15.00, lon_max=15.28)


def _bounds_from_geofences(geofences: list[dict[str, Any]]) -> Bounds:
    patrol = next(
        (g for g in geofences if g.get("type") == "patrol_area"),
        geofences[0] if geofences else None,
    )
    if not patrol:
        return _DEFAULT_BOUNDS
    coords = patrol.get("coordinates") or []
    lats = [float(c.get("lat")) for c in coords if c.get("lat") is not None]
    lons = [float(c.get("lon")) for c in coords if c.get("lon") is not None]
    if not lats or not lons:
        return _DEFAULT_BOUNDS
    return Bounds(lat_min=min(lats), lat_max=max(lats), lon_min=min(lons), lon_max=max(lons))
