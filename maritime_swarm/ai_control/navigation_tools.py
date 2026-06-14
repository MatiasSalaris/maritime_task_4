"""Concrete tools and the default registry.

Tools translate high-level intent into per-tick world actions (heading / speed /
planned_path / current_task). They are **grounded**: ``build()`` validates
arguments against the live observation, shared picture and scene, so the LLM
cannot act on a contact or POI that does not exist.

Symbolic targets (sectors, POI ids, contact ids) are preferred over raw lat/lon
because small models reason about them far more reliably.
"""

from __future__ import annotations

import math
from typing import Any

from maritime_swarm.ai_control import coordination as coord
from maritime_swarm.ai_control.geo import bearing_deg, destination, haversine_km

_COMPASS = {
    "north": 0, "n": 0, "northeast": 45, "ne": 45, "north-east": 45,
    "east": 90, "e": 90, "southeast": 135, "se": 135, "south-east": 135,
    "south": 180, "s": 180, "southwest": 225, "sw": 225, "south-west": 225,
    "west": 270, "w": 270, "northwest": 315, "nw": 315, "north-west": 315,
}
from maritime_swarm.ai_control.observation import Observation
from maritime_swarm.ai_control.tools import (
    Tool,
    ToolContext,
    ToolError,
    ToolInvocation,
    ToolRegistry,
    ToolStatus,
    require_number,
    require_str,
)

_M_PER_DEG_LAT = 111_320.0
_KM_PER_DEG_LAT = 111.32


# ── grounding helpers ─────────────────────────────────────────────────────────
def _known_contact_pos(ctx: ToolContext, contact_id: str) -> tuple[float, float] | None:
    """Position of a contact from the live obs first, then the shared picture."""
    if ctx.obs is not None:
        c = ctx.obs.contact(contact_id)
        if c is not None:
            return (c.lat, c.lon)
    if ctx.view is not None:
        sc = ctx.view.contacts.get(contact_id)
        if sc is not None:
            return (sc.lat, sc.lon)
    return None


def _poi(ctx: ToolContext, poi_id: str):
    if ctx.scene is not None:
        for p in ctx.scene.pois:
            if p.id == poi_id:
                return p
    return None


def _steer(obs: Observation, lat: float, lon: float, ctx: ToolContext, task: str) -> dict[str, Any]:
    return {
        "heading": bearing_deg(obs.lat, obs.lon, lat, lon),
        "speed_kn": ctx.cruise_speed_kn,
        "planned_path": [{"lat": lat, "lon": lon}],
        "current_task": task,
    }


def _stop(task: str) -> dict[str, Any]:
    return {"speed_kn": 0.0, "planned_path": [], "current_task": task}


def _auto_search_box(ctx: ToolContext, sector: str) -> tuple[float, float, float, float]:
    if ctx.bounds is None:
        raise ToolError("search_area needs operating-area bounds")
    b = ctx.bounds
    sec = (sector or "").upper()
    if sec in coord.SECTORS:
        return coord.sector_box(b, sec)
    if sec == "ALL":
        return (b.lat_min, b.lat_max, b.lon_min, b.lon_max)
    if sec == "WEST":
        mid = (b.lon_min + b.lon_max) / 2
        return (b.lat_min, b.lat_max, b.lon_min, mid)
    if sec == "EAST":
        mid = (b.lon_min + b.lon_max) / 2
        return (b.lat_min, b.lat_max, mid, b.lon_max)
    raise ToolError("search_area sector must be an explicit choice: ALL, WEST, EAST, NW, NE, SW, SE or CENTER")


def _search_area_label(ctx: ToolContext, sector: str) -> str:
    sec = (sector or "").upper()
    if sec == "ALL":
        return "tutta l’area"
    return f"settore {sec}"


def _lawnmower_waypoints(
    box: tuple[float, float, float, float],
    spacing_km: float,
    start_lat: float,
    start_lon: float,
) -> list[tuple[float, float]]:
    lo_lat, hi_lat, lo_lon, hi_lon = box
    pad_lat = max((hi_lat - lo_lat) * 0.03, 0.001)
    pad_lon = max((hi_lon - lo_lon) * 0.03, 0.001)
    lo_lat += pad_lat; hi_lat -= pad_lat
    lo_lon += pad_lon; hi_lon -= pad_lon
    if lo_lat >= hi_lat or lo_lon >= hi_lon:
        return [((lo_lat + hi_lat) / 2, (lo_lon + hi_lon) / 2)]

    midlat = (lo_lat + hi_lat) / 2
    km_per_deg_lon = max(20.0, _KM_PER_DEG_LAT * math.cos(math.radians(midlat)))
    step_lon = max(0.001, spacing_km / km_per_deg_lon)

    lons: list[float] = []
    lon = lo_lon
    while lon <= hi_lon:
        lons.append(lon)
        lon += step_lon
    if not lons or (hi_lon - lons[-1]) * km_per_deg_lon > spacing_km * 0.35:
        lons.append(hi_lon)

    points: list[tuple[float, float]] = []
    for i, col_lon in enumerate(lons):
        if i % 2 == 0:
            points.extend([(lo_lat, col_lon), (hi_lat, col_lon)])
        else:
            points.extend([(hi_lat, col_lon), (lo_lat, col_lon)])

    if points and haversine_km(start_lat, start_lon, *points[-1]) < haversine_km(start_lat, start_lon, *points[0]):
        points.reverse()
    return points


# ── go_to (raw waypoint) ───────────────────────────────────────────────────────
class GoToTool(Tool):
    name = "go_to"
    description = "transit to a lat/lon waypoint."
    parameters = {
        "lat": {"type": "number", "description": "target latitude (decimal degrees)"},
        "lon": {"type": "number", "description": "target longitude (decimal degrees)"},
    }

    def __init__(self, lat: float, lon: float) -> None:
        self.lat, self.lon = lat, lon

    @classmethod
    def build(cls, args: dict[str, Any], ctx: ToolContext) -> "GoToTool":
        lat, lon = require_number(args, "lat"), require_number(args, "lon")
        if ctx.bounds is not None:
            lat, lon = ctx.bounds.clamp_point(lat, lon)
        return cls(lat, lon)

    def step(self, obs: Observation, ctx: ToolContext) -> ToolInvocation:
        dist = haversine_km(obs.lat, obs.lon, self.lat, self.lon)
        if dist <= ctx.arrival_km:
            return ToolInvocation(_stop(f"In posizione @ {self.lat:.3f}, {self.lon:.3f}"), ToolStatus.DONE, "arrived")
        return ToolInvocation(
            _steer(obs, self.lat, self.lon, ctx, f"Vai a {self.lat:.3f}, {self.lon:.3f} ({dist:.1f} km)"),
            ToolStatus.RUNNING, f"{dist:.2f} km",
        )

    def describe(self) -> str:
        return f"go_to({self.lat:.4f}, {self.lon:.4f})"


# ── move (relative, directional) ───────────────────────────────────────────────
class MoveTool(Tool):
    name = "move"
    description = "move a distance in a compass direction from your current position (e.g. 5 km south)."
    parameters = {
        "direction": {"type": "string", "description": "compass direction (north, south, east, west, NE, NW, SE, SW) or a bearing in degrees"},
        "distance_km": {"type": "number", "description": "how far to move, in kilometres", "required": False},
    }

    def __init__(self, lat: float, lon: float, label: str) -> None:
        self.lat, self.lon, self._label = lat, lon, label

    @classmethod
    def build(cls, args: dict[str, Any], ctx: ToolContext) -> "MoveTool":
        raw = require_str(args, "direction").lower().strip()
        if raw in _COMPASS:
            bearing = float(_COMPASS[raw])
        else:
            try:
                bearing = float(raw) % 360.0
            except ValueError:
                raise ToolError(f"unknown direction '{raw}'")
        dist = float(args.get("distance_km") or 5.0)
        dist = max(0.3, min(60.0, dist))
        if ctx.obs is None:
            raise ToolError("move needs a current position")
        lat, lon = destination(ctx.obs.lat, ctx.obs.lon, bearing, dist)
        if ctx.bounds is not None:
            lat, lon = ctx.bounds.clamp_point(lat, lon)
        return cls(lat, lon, f"{dist:.0f}km bearing {bearing:.0f}")

    def step(self, obs: Observation, ctx: ToolContext) -> ToolInvocation:
        dist = haversine_km(obs.lat, obs.lon, self.lat, self.lon)
        if dist <= ctx.arrival_km:
            return ToolInvocation(_stop(f"In posizione @ {self.lat:.3f}, {self.lon:.3f}"), ToolStatus.DONE, "arrived")
        return ToolInvocation(
            _steer(obs, self.lat, self.lon, ctx, f"Procedo {self._label} -> {self.lat:.3f}, {self.lon:.3f}"),
            ToolStatus.RUNNING, f"{dist:.2f} km")

    def describe(self) -> str:
        return f"move({self._label})"


# ── go_to_poi (symbolic) ───────────────────────────────────────────────────────
class GoToPoiTool(Tool):
    name = "go_to_poi"
    description = "go to a point of interest by its id."
    parameters = {
        "poi_id": {"type": "string", "description": "id of a POI from the operating-area list (e.g. 'poi_1')"},
    }

    def __init__(self, poi_id: str, lat: float, lon: float) -> None:
        self.poi_id, self.lat, self.lon = poi_id, lat, lon

    @classmethod
    def build(cls, args: dict[str, Any], ctx: ToolContext) -> "GoToPoiTool":
        pid = require_str(args, "poi_id")
        p = _poi(ctx, pid)
        if p is None:
            raise ToolError(f"unknown poi '{pid}'")
        return cls(pid, p.lat, p.lon)

    def step(self, obs: Observation, ctx: ToolContext) -> ToolInvocation:
        dist = haversine_km(obs.lat, obs.lon, self.lat, self.lon)
        if dist <= ctx.arrival_km:
            return ToolInvocation(_stop(f"In posizione @ {self.poi_id}"), ToolStatus.DONE, "arrived")
        return ToolInvocation(
            _steer(obs, self.lat, self.lon, ctx, f"Vai a {self.poi_id} ({dist:.1f} km)"),
            ToolStatus.RUNNING, f"{dist:.2f} km",
        )

    def describe(self) -> str:
        return f"go_to_poi({self.poi_id})"


# ── patrol_sector (continuous baseline) ────────────────────────────────────────
class PatrolSectorTool(Tool):
    name = "patrol_sector"
    description = "continuously patrol a named sector (NW/NE/SW/SE/CENTER)."
    parameters = {
        "sector": {"type": "string", "description": "one of NW, NE, SW, SE, CENTER"},
    }

    def __init__(self, sector: str) -> None:
        self.sector = sector
        self._waypoints: list[tuple[float, float]] = []
        self._bounds_key: tuple[float, float, float, float] | None = None
        self._idx = 0

    @classmethod
    def build(cls, args: dict[str, Any], ctx: ToolContext) -> "PatrolSectorTool":
        sec = require_str(args, "sector").upper()
        if sec not in coord.SECTORS:
            raise ToolError(f"unknown sector '{sec}', expected one of {coord.SECTORS}")
        return cls(sec)

    def _ensure_wp(self, ctx: ToolContext) -> None:
        if ctx.bounds is None:
            return
        key = (
            round(ctx.bounds.lat_min, 7),
            round(ctx.bounds.lat_max, 7),
            round(ctx.bounds.lon_min, 7),
            round(ctx.bounds.lon_max, 7),
        )
        if key != self._bounds_key:
            self._bounds_key = key
            self._waypoints = coord.sector_waypoints(ctx.bounds, self.sector)
            self._idx = 0

    def step(self, obs: Observation, ctx: ToolContext) -> ToolInvocation:
        self._ensure_wp(ctx)
        if not self._waypoints:
            return ToolInvocation(_stop(f"Pattuglia {self.sector}"), ToolStatus.RUNNING, "no bounds")
        tlat, tlon = self._waypoints[self._idx % len(self._waypoints)]
        if haversine_km(obs.lat, obs.lon, tlat, tlon) <= ctx.arrival_km:
            self._idx += 1
            tlat, tlon = self._waypoints[self._idx % len(self._waypoints)]
        return ToolInvocation(
            _steer(obs, tlat, tlon, ctx, f"Pattuglia settore {self.sector}"),
            ToolStatus.RUNNING, f"leg {self._idx % len(self._waypoints)}",
        )

    def describe(self) -> str:
        return f"patrol_sector({self.sector})"


# ── search_area (coverage search) ─────────────────────────────────────────────
class SearchAreaTool(Tool):
    name = "search_area"
    description = (
        "coverage search using a lawn-mower pattern inside an explicit operating-area sector. "
        "Use for finding a missing buoy or unknown object after choosing a sector from current state."
    )
    parameters = {
        "sector": {
            "type": "string",
            "description": "ALL, WEST, EAST, NW, NE, SW, SE or CENTER. Choose explicitly from current state.",
        },
        "spacing_km": {
            "type": "number",
            "description": "distance between sweep lines. Omit to use sensor range with overlap.",
            "required": False,
        },
        "priority": {
            "type": "string",
            "description": "coverage for dense overlap, speed for fewer wider sweep lines, balanced by default.",
            "required": False,
        },
    }

    def __init__(self, sector: str, spacing_km: float | None = None, priority: str = "balanced") -> None:
        self.sector = sector.upper()
        self.spacing_km = spacing_km
        self.priority = priority.lower().strip() or "balanced"
        self._waypoints: list[tuple[float, float]] = []
        self._key: tuple[Any, ...] | None = None
        self._idx = 0

    @classmethod
    def build(cls, args: dict[str, Any], ctx: ToolContext) -> "SearchAreaTool":
        sector = str(args.get("sector") or "").upper().strip()
        if not sector or sector == "AUTO":
            raise ToolError("search_area requires an explicit sector chosen from current state; AUTO is not allowed")
        spacing = args.get("spacing_km")
        spacing_km = None if spacing is None else max(0.3, min(20.0, float(spacing)))
        priority = str(args.get("priority") or "balanced").lower().strip()
        if priority not in {"speed", "coverage", "balanced"}:
            priority = "balanced"
        _auto_search_box(ctx, sector)  # validate sector/bounds now, not after build
        return cls(sector, spacing_km, priority)

    def _effective_spacing(self, ctx: ToolContext) -> float:
        if self.spacing_km is not None:
            return self.spacing_km
        # Swath width is roughly 2R. Coverage overlaps more; speed accepts a
        # coarser first pass so the target is found quickly in the demo.
        factor = {"coverage": 0.9, "balanced": 1.4, "speed": 1.9}.get(self.priority, 1.4)
        return max(0.4, min(20.0, ctx.sensor_range_km * factor))

    def _ensure_plan(self, obs: Observation, ctx: ToolContext) -> None:
        if ctx.bounds is None:
            return
        spacing = self._effective_spacing(ctx)
        box = _auto_search_box(ctx, self.sector)
        key = (
            self.sector,
            self.priority,
            round(spacing, 3),
            round(box[0], 7), round(box[1], 7), round(box[2], 7), round(box[3], 7),
        )
        if key == self._key:
            return
        self._key = key
        self._waypoints = _lawnmower_waypoints(box, spacing, obs.lat, obs.lon)
        self._idx = 0

    def step(self, obs: Observation, ctx: ToolContext) -> ToolInvocation:
        self._ensure_plan(obs, ctx)
        if not self._waypoints:
            return ToolInvocation(_stop("Ricerca area: nessun waypoint"), ToolStatus.FAILED, "no plan")

        while self._idx < len(self._waypoints):
            tlat, tlon = self._waypoints[self._idx]
            if haversine_km(obs.lat, obs.lon, tlat, tlon) > ctx.arrival_km:
                break
            self._idx += 1

        if self._idx >= len(self._waypoints):
            return ToolInvocation(_stop(f"Ricerca completata {self.sector}"), ToolStatus.DONE, "complete")

        tlat, tlon = self._waypoints[self._idx]
        remaining = [{"lat": lat, "lon": lon} for lat, lon in self._waypoints[self._idx:self._idx + 24]]
        return ToolInvocation({
            "heading": bearing_deg(obs.lat, obs.lon, tlat, tlon),
            "speed_kn": ctx.cruise_speed_kn,
            "planned_path": remaining,
            "current_task": f"Ricerca {_search_area_label(ctx, self.sector)} priorità {self.priority} passaggio {self._idx + 1}/{len(self._waypoints)}",
        }, ToolStatus.RUNNING, f"line {self._idx + 1}/{len(self._waypoints)}")

    def describe(self) -> str:
        return f"search_area({self.sector}, {self.priority})"


# ── investigate_contact (reactive) ─────────────────────────────────────────────
class InvestigateContactTool(Tool):
    name = "investigate_contact"
    description = "close on a known contact (by id) to identify it."
    parameters = {
        "contact_id": {"type": "string", "description": "id of a contact in sensor range or the shared picture"},
    }

    def __init__(self, contact_id: str) -> None:
        self.contact_id = contact_id
        self._last: tuple[float, float] | None = None

    @classmethod
    def build(cls, args: dict[str, Any], ctx: ToolContext) -> "InvestigateContactTool":
        cid = require_str(args, "contact_id")
        if _known_contact_pos(ctx, cid) is None:
            raise ToolError(f"contact '{cid}' is not sensed or known — cannot investigate")
        return cls(cid)

    def step(self, obs: Observation, ctx: ToolContext) -> ToolInvocation:
        pos = _known_contact_pos(ctx, self.contact_id)
        if pos is not None:
            self._last = pos
        if self._last is None:
            return ToolInvocation(None, ToolStatus.FAILED, f"lost {self.contact_id}")
        tlat, tlon = self._last
        dist = haversine_km(obs.lat, obs.lon, tlat, tlon)
        if dist <= max(ctx.arrival_km, ctx.identify_km):
            # Close enough for the sensor to identify it — no need to physically touch it.
            return ToolInvocation(_stop(f"Identificato {self.contact_id}"), ToolStatus.DONE, "identified")
        return ToolInvocation(
            _steer(obs, tlat, tlon, ctx, f"Ispeziona {self.contact_id} ({dist:.1f} km)"),
            ToolStatus.RUNNING, f"{dist:.2f} km",
        )

    def describe(self) -> str:
        return f"investigate_contact({self.contact_id})"


# ── report_contact (reactive, emits a P2P anomaly report) ──────────────────────
class ReportContactTool(Tool):
    name = "report_contact"
    description = "report a contact with a classification and one-line rationale."
    parameters = {
        "contact_id": {"type": "string", "description": "id of the contact being reported"},
        "classification": {"type": "string", "description": "your assessment, e.g. ANOMALY / SUSPICIOUS / BENIGN"},
        "rationale": {"type": "string", "description": "one short sentence justifying the assessment from the evidence"},
    }

    def __init__(self, contact_id: str, classification: str, rationale: str, pos: tuple[float, float]) -> None:
        self.contact_id = contact_id
        self.classification = classification
        self.rationale = rationale
        self.pos = pos

    @classmethod
    def build(cls, args: dict[str, Any], ctx: ToolContext) -> "ReportContactTool":
        cid = require_str(args, "contact_id")
        pos = _known_contact_pos(ctx, cid)
        if pos is None:
            raise ToolError(f"contact '{cid}' is not sensed or known — cannot report")
        classification = require_str(args, "classification").upper()
        rationale = str(args.get("rationale") or "").strip() or "no rationale given"
        return cls(cid, classification, rationale, pos)

    def step(self, obs: Observation, ctx: ToolContext) -> ToolInvocation:
        lat, lon = self.pos
        p2p = {
            "to": "all",
            "msg_type": "report",
            "content": {
                "report": {
                    "contact_id": self.contact_id,
                    "classification": self.classification,
                    "rationale": self.rationale,
                    "pos": {"lat": lat, "lon": lon},
                },
                # also surface as a shared-picture update
                "contacts": [{
                    "id": self.contact_id, "lat": lat, "lon": lon,
                    "classification": self.classification, "reported": True,
                }],
            },
            "reasoning": f"{self.contact_id}: {self.classification} — {self.rationale}",
        }
        return ToolInvocation(
            _stop(f"Segnalato {self.contact_id} ({self.classification})"),
            ToolStatus.DONE, "reported", p2p=p2p,
        )

    def describe(self) -> str:
        return f"report_contact({self.contact_id}, {self.classification})"


# ── escort_contact (continuous station-keeping at a standoff) ──────────────────
class EscortContactTool(Tool):
    name = "escort_contact"
    description = "shadow/escort a contact at a standoff distance and relative bearing."
    parameters = {
        "contact_id": {"type": "string", "description": "id of the vessel to escort"},
        "standoff_m": {"type": "number", "description": "standoff distance in metres (e.g. 500)", "required": False},
        "bearing_deg": {"type": "number", "description": "relative bearing to hold from the contact, 0-360", "required": False},
    }

    def __init__(self, contact_id: str, standoff_m: float, bearing_deg: float) -> None:
        self.contact_id = contact_id
        self.standoff_m = standoff_m
        self.bearing_deg = bearing_deg
        self._last: tuple[float, float] | None = None

    @classmethod
    def build(cls, args: dict[str, Any], ctx: ToolContext) -> "EscortContactTool":
        cid = require_str(args, "contact_id")
        if _known_contact_pos(ctx, cid) is None:
            raise ToolError(f"contact '{cid}' is not sensed or known — cannot escort")
        standoff = float(args.get("standoff_m") or 500.0)
        standoff = max(100.0, min(3000.0, standoff))
        bearing = float(args.get("bearing_deg") or 0.0) % 360.0
        return cls(cid, standoff, bearing)

    def _station(self, clat: float, clon: float) -> tuple[float, float]:
        d_deg = self.standoff_m / _M_PER_DEG_LAT
        rad = math.radians(self.bearing_deg)
        dlat = d_deg * math.cos(rad)
        dlon = d_deg * math.sin(rad) / max(0.2, math.cos(math.radians(clat)))
        return (clat + dlat, clon + dlon)

    def step(self, obs: Observation, ctx: ToolContext) -> ToolInvocation:
        pos = _known_contact_pos(ctx, self.contact_id)
        if pos is not None:
            self._last = pos
        if self._last is None:
            return ToolInvocation(None, ToolStatus.FAILED, f"lost {self.contact_id}")
        slat, slon = self._station(*self._last)
        dist = haversine_km(obs.lat, obs.lon, slat, slon)
        task = f"Segue {self.contact_id} @ {int(self.standoff_m)}m / {int(self.bearing_deg)}°"
        if dist <= ctx.arrival_km:
            return ToolInvocation(_stop(task + " (in posizione)"), ToolStatus.RUNNING, "on station")
        return ToolInvocation(_steer(obs, slat, slon, ctx, task), ToolStatus.RUNNING, f"{dist:.2f} km to station")

    def describe(self) -> str:
        return f"escort_contact({self.contact_id}, {int(self.standoff_m)}m)"


# ── visit_pois (sequential investigation, then optional rendezvous) ────────────
class VisitPoisTool(Tool):
    name = "visit_pois"
    description = "visit POIs in the given order, then optionally rendezvous."
    parameters = {
        "poi_ids": {"type": "array", "description": "ordered list of POI ids to visit"},
        "rendezvous": {"type": "string", "description": "POI id to converge on after the sequence", "required": False},
    }

    def __init__(self, poi_ids: list[str], rendezvous: str | None, points: dict[str, tuple[float, float]]) -> None:
        self.poi_ids = poi_ids
        self.rendezvous = rendezvous
        self.points = points
        self._idx = 0

    @classmethod
    def build(cls, args: dict[str, Any], ctx: ToolContext) -> "VisitPoisTool":
        raw = args.get("poi_ids")
        if not isinstance(raw, list) or not raw:
            raise ToolError("poi_ids must be a non-empty list")
        ids = [str(x) for x in raw]
        points: dict[str, tuple[float, float]] = {}
        for pid in ids:
            p = _poi(ctx, pid)
            if p is None:
                raise ToolError(f"unknown poi '{pid}'")
            points[pid] = (p.lat, p.lon)
        rdv = args.get("rendezvous")
        if rdv:
            rp = _poi(ctx, str(rdv))
            if rp is None:
                raise ToolError(f"unknown rendezvous poi '{rdv}'")
            points[str(rdv)] = (rp.lat, rp.lon)
            rdv = str(rdv)
        return cls(ids, rdv, points)

    def step(self, obs: Observation, ctx: ToolContext) -> ToolInvocation:
        seq = list(self.poi_ids) + ([self.rendezvous] if self.rendezvous else [])
        if self._idx >= len(seq):
            return ToolInvocation(_stop("Sequenza completata: mantengo posizione"), ToolStatus.RUNNING, "done")
        target_id = seq[self._idx]
        tlat, tlon = self.points[target_id]
        dist = haversine_km(obs.lat, obs.lon, tlat, tlon)
        if dist <= ctx.arrival_km:
            self._idx += 1
            label = "Rendezvous raggiunto" if (self.rendezvous and self._idx >= len(seq)) else f"Raggiunto {target_id}"
            return ToolInvocation(_stop(label), ToolStatus.RUNNING, f"reached {target_id}")
        last = self._idx == len(seq) - 1 and self.rendezvous
        verb = "Rendezvous a" if last else "Visita"
        return ToolInvocation(
            _steer(obs, tlat, tlon, ctx, f"{verb} {target_id} ({dist:.1f} km)"),
            ToolStatus.RUNNING, f"{dist:.2f} km",
        )

    def describe(self) -> str:
        return f"visit_pois({'→'.join(self.poi_ids)})"


# ── rendezvous (converge on a point) ───────────────────────────────────────────
class RendezvousTool(Tool):
    name = "rendezvous"
    description = "converge on a rendezvous point (a POI id)."
    parameters = {
        "poi_id": {"type": "string", "description": "POI id to converge on"},
    }

    def __init__(self, poi_id: str, lat: float, lon: float) -> None:
        self.poi_id, self.lat, self.lon = poi_id, lat, lon

    @classmethod
    def build(cls, args: dict[str, Any], ctx: ToolContext) -> "RendezvousTool":
        pid = require_str(args, "poi_id")
        p = _poi(ctx, pid)
        if p is None:
            raise ToolError(f"unknown rendezvous poi '{pid}'")
        return cls(pid, p.lat, p.lon)

    def step(self, obs: Observation, ctx: ToolContext) -> ToolInvocation:
        dist = haversine_km(obs.lat, obs.lon, self.lat, self.lon)
        if dist <= ctx.arrival_km:
            return ToolInvocation(_stop(f"Al rendezvous {self.poi_id}"), ToolStatus.RUNNING, "arrived")
        return ToolInvocation(
            _steer(obs, self.lat, self.lon, ctx, f"Rendezvous a {self.poi_id} ({dist:.1f} km)"),
            ToolStatus.RUNNING, f"{dist:.2f} km",
        )

    def describe(self) -> str:
        return f"rendezvous({self.poi_id})"


# ── hold_position ──────────────────────────────────────────────────────────────
class HoldPositionTool(Tool):
    name = "hold_position"
    description = "stop and hold position for N seconds to observe."
    parameters = {
        "seconds": {"type": "number", "description": "how long to hold (default 20)", "required": False},
    }

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self._start: float | None = None

    @classmethod
    def build(cls, args: dict[str, Any], ctx: ToolContext) -> "HoldPositionTool":
        seconds = 20.0
        if args.get("seconds") is not None:
            seconds = require_number(args, "seconds")
        return cls(max(5.0, min(120.0, seconds)))

    def step(self, obs: Observation, ctx: ToolContext) -> ToolInvocation:
        if self._start is None:
            self._start = obs.world_time
        elapsed = obs.world_time - self._start
        if elapsed >= self.seconds:
            return ToolInvocation(_stop("Attesa completata"), ToolStatus.DONE, "elapsed")
        return ToolInvocation(_stop(f"In attesa ({int(self.seconds - elapsed)}s)"), ToolStatus.RUNNING, "holding")

    def describe(self) -> str:
        return f"hold_position({self.seconds:.0f}s)"


def default_registry() -> ToolRegistry:
    """Default tools exposed to each agent."""
    registry = ToolRegistry()
    for tool in (
        GoToTool, MoveTool, GoToPoiTool, SearchAreaTool, PatrolSectorTool,
        InvestigateContactTool, ReportContactTool, EscortContactTool,
        VisitPoisTool, RendezvousTool, HoldPositionTool,
    ):
        registry.register(tool)
    return registry
