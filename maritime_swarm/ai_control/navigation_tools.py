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


# ── go_to (raw waypoint) ───────────────────────────────────────────────────────
class GoToTool(Tool):
    name = "go_to"
    description = "Transit to a geographic waypoint (lat, lon) and hold there on arrival."
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
            return ToolInvocation(_stop(f"On station @ {self.lat:.3f}, {self.lon:.3f}"), ToolStatus.DONE, "arrived")
        return ToolInvocation(
            _steer(obs, self.lat, self.lon, ctx, f"Transit to {self.lat:.3f}, {self.lon:.3f} ({dist:.1f} km)"),
            ToolStatus.RUNNING, f"{dist:.2f} km",
        )

    def describe(self) -> str:
        return f"go_to({self.lat:.4f}, {self.lon:.4f})"


# ── move (relative, directional) ───────────────────────────────────────────────
class MoveTool(Tool):
    name = "move"
    description = ("Move a distance in a compass direction from your CURRENT position "
                   "(e.g. 5 km south). Use for directional/relative orders.")
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
            return ToolInvocation(_stop(f"On station @ {self.lat:.3f}, {self.lon:.3f}"), ToolStatus.DONE, "arrived")
        return ToolInvocation(
            _steer(obs, self.lat, self.lon, ctx, f"Proceeding {self._label} → {self.lat:.3f}, {self.lon:.3f}"),
            ToolStatus.RUNNING, f"{dist:.2f} km")

    def describe(self) -> str:
        return f"move({self._label})"


# ── go_to_poi (symbolic) ───────────────────────────────────────────────────────
class GoToPoiTool(Tool):
    name = "go_to_poi"
    description = "Transit to a named point of interest by its id, and hold there on arrival."
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
            return ToolInvocation(_stop(f"On station @ {self.poi_id}"), ToolStatus.DONE, "arrived")
        return ToolInvocation(
            _steer(obs, self.lat, self.lon, ctx, f"Transit to {self.poi_id} ({dist:.1f} km)"),
            ToolStatus.RUNNING, f"{dist:.2f} km",
        )

    def describe(self) -> str:
        return f"go_to_poi({self.poi_id})"


# ── patrol_sector (continuous baseline) ────────────────────────────────────────
class PatrolSectorTool(Tool):
    name = "patrol_sector"
    description = (
        "Continuously patrol a named sector of the operating area "
        "(NW, NE, SW, SE or CENTER), sweeping it for coverage. Runs indefinitely."
    )
    parameters = {
        "sector": {"type": "string", "description": "one of NW, NE, SW, SE, CENTER"},
    }

    def __init__(self, sector: str) -> None:
        self.sector = sector
        self._waypoints: list[tuple[float, float]] = []
        self._idx = 0

    @classmethod
    def build(cls, args: dict[str, Any], ctx: ToolContext) -> "PatrolSectorTool":
        sec = require_str(args, "sector").upper()
        if sec not in coord.SECTORS:
            raise ToolError(f"unknown sector '{sec}', expected one of {coord.SECTORS}")
        return cls(sec)

    def _ensure_wp(self, ctx: ToolContext) -> None:
        if not self._waypoints and ctx.bounds is not None:
            self._waypoints = coord.sector_waypoints(ctx.bounds, self.sector)

    def step(self, obs: Observation, ctx: ToolContext) -> ToolInvocation:
        self._ensure_wp(ctx)
        if not self._waypoints:
            return ToolInvocation(_stop(f"Patrolling {self.sector}"), ToolStatus.RUNNING, "no bounds")
        tlat, tlon = self._waypoints[self._idx % len(self._waypoints)]
        if haversine_km(obs.lat, obs.lon, tlat, tlon) <= ctx.arrival_km:
            self._idx += 1
            tlat, tlon = self._waypoints[self._idx % len(self._waypoints)]
        return ToolInvocation(
            _steer(obs, tlat, tlon, ctx, f"Patrolling sector {self.sector}"),
            ToolStatus.RUNNING, f"leg {self._idx % len(self._waypoints)}",
        )

    def describe(self) -> str:
        return f"patrol_sector({self.sector})"


# ── investigate_contact (reactive) ─────────────────────────────────────────────
class InvestigateContactTool(Tool):
    name = "investigate_contact"
    description = (
        "Close on a known contact (by id) to identify it. Completes on arrival; "
        "the contact must currently be sensed or in the shared picture."
    )
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
            return ToolInvocation(_stop(f"Identified {self.contact_id}"), ToolStatus.DONE, "identified")
        return ToolInvocation(
            _steer(obs, tlat, tlon, ctx, f"Intercepting {self.contact_id} ({dist:.1f} km)"),
            ToolStatus.RUNNING, f"{dist:.2f} km",
        )

    def describe(self) -> str:
        return f"investigate_contact({self.contact_id})"


# ── report_contact (reactive, emits a P2P anomaly report) ──────────────────────
class ReportContactTool(Tool):
    name = "report_contact"
    description = (
        "Report a contact to the team with an assessment and a rationale "
        "(e.g. flagging a vessel that does not match a commercial AIS pattern)."
    )
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
            _stop(f"Reported {self.contact_id} ({self.classification})"),
            ToolStatus.DONE, "reported", p2p=p2p,
        )

    def describe(self) -> str:
        return f"report_contact({self.contact_id}, {self.classification})"


# ── escort_contact (continuous station-keeping at a standoff) ──────────────────
class EscortContactTool(Tool):
    name = "escort_contact"
    description = (
        "Escort a contact by holding station at a standoff distance and relative "
        "bearing from it (loose formation). Runs continuously."
    )
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
        task = f"Escorting {self.contact_id} @ {int(self.standoff_m)}m / {int(self.bearing_deg)}°"
        if dist <= ctx.arrival_km:
            return ToolInvocation(_stop(task + " (on station)"), ToolStatus.RUNNING, "on station")
        return ToolInvocation(_steer(obs, slat, slon, ctx, task), ToolStatus.RUNNING, f"{dist:.2f} km to station")

    def describe(self) -> str:
        return f"escort_contact({self.contact_id}, {int(self.standoff_m)}m)"


# ── visit_pois (sequential investigation, then optional rendezvous) ────────────
class VisitPoisTool(Tool):
    name = "visit_pois"
    description = (
        "Visit a list of POIs in the given order, then optionally hold at a "
        "rendezvous POI. Runs until done, then holds at the last point."
    )
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
            return ToolInvocation(_stop("Sequence complete — holding"), ToolStatus.RUNNING, "done")
        target_id = seq[self._idx]
        tlat, tlon = self.points[target_id]
        dist = haversine_km(obs.lat, obs.lon, tlat, tlon)
        if dist <= ctx.arrival_km:
            self._idx += 1
            label = "Rendezvous reached" if (self.rendezvous and self._idx >= len(seq)) else f"Reached {target_id}"
            return ToolInvocation(_stop(label), ToolStatus.RUNNING, f"reached {target_id}")
        last = self._idx == len(seq) - 1 and self.rendezvous
        verb = "Rendezvous at" if last else "Visiting"
        return ToolInvocation(
            _steer(obs, tlat, tlon, ctx, f"{verb} {target_id} ({dist:.1f} km)"),
            ToolStatus.RUNNING, f"{dist:.2f} km",
        )

    def describe(self) -> str:
        return f"visit_pois({'→'.join(self.poi_ids)})"


# ── rendezvous (converge on a point) ───────────────────────────────────────────
class RendezvousTool(Tool):
    name = "rendezvous"
    description = "Converge on a rendezvous point (a POI id) and hold there."
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
            return ToolInvocation(_stop(f"At rendezvous {self.poi_id}"), ToolStatus.RUNNING, "arrived")
        return ToolInvocation(
            _steer(obs, self.lat, self.lon, ctx, f"Rendezvous at {self.poi_id} ({dist:.1f} km)"),
            ToolStatus.RUNNING, f"{dist:.2f} km",
        )

    def describe(self) -> str:
        return f"rendezvous({self.poi_id})"


# ── hold_position ──────────────────────────────────────────────────────────────
class HoldPositionTool(Tool):
    name = "hold_position"
    description = "Stop and hold the current position for a number of seconds to observe."
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
            return ToolInvocation(_stop("Hold complete"), ToolStatus.DONE, "elapsed")
        return ToolInvocation(_stop(f"Holding ({int(self.seconds - elapsed)}s)"), ToolStatus.RUNNING, "holding")

    def describe(self) -> str:
        return f"hold_position({self.seconds:.0f}s)"


def default_registry() -> ToolRegistry:
    """The full maritime toolset (covers patrol/report, escort, search & rendezvous)."""
    registry = ToolRegistry()
    for tool in (
        GoToTool, MoveTool, GoToPoiTool, PatrolSectorTool, InvestigateContactTool,
        ReportContactTool, EscortContactTool, VisitPoisTool, RendezvousTool,
        HoldPositionTool,
    ):
        registry.register(tool)
    return registry
