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
    source: str = "default"

    @classmethod
    def from_world_state(cls, state: dict[str, Any]) -> "Scene":
        bounds, source = _bounds_from_state(state)
        pois = [
            POI(
                id=str(p.get("id", "")),
                label=str(p.get("label", "")),
                lat=float((p.get("position") or {}).get("lat", 0.0)),
                lon=float((p.get("position") or {}).get("lon", 0.0)),
            )
            for p in state.get("pois", [])
        ]
        return cls(bounds=bounds, pois=pois, source=source)

    def with_aor(self, aor: dict[str, Any] | None) -> "Scene":
        if not aor:
            return self
        bounds = _bounds_from_aor(aor)
        if bounds is None:
            return self
        return Scene(bounds=bounds, pois=self.pois, source="selected AOR")


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


def _bounds_from_state(state: dict[str, Any]) -> tuple[Bounds, str]:
    aor_bounds = _bounds_from_aor(state.get("aor"))
    if aor_bounds is not None:
        return aor_bounds, "selected AOR"
    return _bounds_from_geofences(state.get("geofences", [])), "patrol geofence"


def _bounds_from_aor(aor: dict[str, Any] | None) -> Bounds | None:
    """Return the bbox of a GeoJSON Polygon AOR, or None if invalid.

    The frontend sends GeoJSON coordinates as [lon, lat]. The current patrol
    tools operate on rectangular bounds, so this deliberately uses the AOR bbox:
    good enough for rectangle/circle/poly selections and much better than
    ignoring the operator-marked area.
    """
    if not isinstance(aor, dict) or aor.get("type") != "Polygon":
        return None
    rings = aor.get("coordinates") or []
    if not rings or not isinstance(rings[0], list):
        return None
    lats: list[float] = []
    lons: list[float] = []
    for pt in rings[0]:
        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
            continue
        try:
            lon, lat = float(pt[0]), float(pt[1])
        except (TypeError, ValueError):
            continue
        lats.append(lat)
        lons.append(lon)
    if not lats or not lons:
        return None
    return Bounds(lat_min=min(lats), lat_max=max(lats), lon_min=min(lons), lon_max=max(lons))
