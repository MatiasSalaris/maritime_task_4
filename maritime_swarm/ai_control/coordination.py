"""Coordination primitives: sectors, the assignment model, and a thin grounded
de-confliction backstop.

The negotiation itself is LLM-driven (proposals / objections / acks exchanged
over the P2P bus). This module provides the *grounded* scaffolding that keeps
that negotiation convergent and bound to the real world:

- a fixed set of named **sectors** (quadrants + centre) so agents can divide an
  area symbolically instead of inventing raw coordinates;
- an **assignment** schema (a small dict) covering every reference scenario;
- a last-resort **de-confliction** that runs identically inside every agent, so
  if the LLM leaves two assets on the same sector they still converge to a clean
  split without any central authority.
"""

from __future__ import annotations

from typing import Any

from maritime_swarm.ai_control.geo import haversine_km
from maritime_swarm.ai_control.tools import Bounds

SECTORS = ["NW", "NE", "SW", "SE", "CENTER"]


def sector_box(b: Bounds, sector: str) -> tuple[float, float, float, float]:
    """Return (lat_min, lat_max, lon_min, lon_max) for a named sector."""
    midlat = (b.lat_min + b.lat_max) / 2
    midlon = (b.lon_min + b.lon_max) / 2
    s = (sector or "").upper()
    if s == "NW":
        return (midlat, b.lat_max, b.lon_min, midlon)
    if s == "NE":
        return (midlat, b.lat_max, midlon, b.lon_max)
    if s == "SW":
        return (b.lat_min, midlat, b.lon_min, midlon)
    if s == "SE":
        return (b.lat_min, midlat, midlon, b.lon_max)
    # CENTER: central 40% box
    dlat = (b.lat_max - b.lat_min) * 0.3
    dlon = (b.lon_max - b.lon_min) * 0.3
    return (b.lat_min + dlat, b.lat_max - dlat, b.lon_min + dlon, b.lon_max - dlon)


def sector_center(b: Bounds, sector: str) -> tuple[float, float]:
    lo_lat, hi_lat, lo_lon, hi_lon = sector_box(b, sector)
    return ((lo_lat + hi_lat) / 2, (lo_lon + hi_lon) / 2)


def sector_waypoints(b: Bounds, sector: str) -> list[tuple[float, float]]:
    """A small lawn-mower-ish loop of waypoints covering a sector."""
    lo_lat, hi_lat, lo_lon, hi_lon = sector_box(b, sector)
    pad_lat = (hi_lat - lo_lat) * 0.18
    pad_lon = (hi_lon - lo_lon) * 0.18
    lo_lat += pad_lat; hi_lat -= pad_lat
    lo_lon += pad_lon; hi_lon -= pad_lon
    midlat = (lo_lat + hi_lat) / 2
    return [
        (hi_lat, lo_lon), (hi_lat, hi_lon),
        (midlat, hi_lon), (midlat, lo_lon),
        (lo_lat, lo_lon), (lo_lat, hi_lon),
    ]


def assignment_label(a: dict[str, Any] | None) -> str:
    """Short human label for an assignment (used as the UI tag / status)."""
    if not a:
        return "UNASSIGNED"
    kind = (a.get("kind") or "").lower()
    if kind == "patrol_sector":
        return f"PATROL {str(a.get('sector', '?')).upper()}"
    if kind == "investigate":
        return f"INVESTIGATE {a.get('contact_id', '?')}"
    if kind == "report":
        return f"REPORT {a.get('contact_id', '?')}"
    if kind == "escort":
        return f"ESCORT {a.get('contact_id', '?')} @{int(a.get('standoff_m', 500))}m"
    if kind == "visit_pois":
        seq = "→".join(a.get("poi_ids", []) or [])
        rdv = a.get("rendezvous")
        return f"VISIT {seq}" + (f" ⇒ {rdv}" if rdv else "")
    if kind == "rendezvous":
        return f"RENDEZVOUS {a.get('poi_id') or a.get('point') or ''}".strip()
    if kind == "go_to":
        return f"PROCEED {a.get('lat', 0):.3f},{a.get('lon', 0):.3f}"
    if kind == "hold":
        return "HOLD"
    return kind.upper() or "UNASSIGNED"


def default_allocation(member_ids: list[str], _bounds: Bounds) -> dict[str, dict[str, Any]]:
    """Deterministic seed allocation: spread members across sectors.

    Used as the leader's starting point and as the convergence fallback.
    """
    quadrants = ["NW", "NE", "SW", "SE"]
    alloc: dict[str, dict[str, Any]] = {}
    for i, aid in enumerate(sorted(member_ids)):
        sector = quadrants[i % len(quadrants)] if i < len(quadrants) else "CENTER"
        alloc[aid] = {"kind": "patrol_sector", "sector": sector}
    return alloc


def deconflict(
    allocation: dict[str, dict[str, Any]],
    member_ids: list[str],
    positions: dict[str, tuple[float, float]],
    bounds: Bounds,
) -> dict[str, dict[str, Any]]:
    """Resolve duplicate *exclusive* sector claims so no two assets patrol the
    same quadrant. Runs identically in every agent → decentralised convergence.

    Only `patrol_sector` is treated as exclusive; investigate/escort/visit can
    legitimately overlap and are left to the LLM negotiation.
    """
    result: dict[str, dict[str, Any]] = {
        aid: dict(allocation.get(aid) or {}) for aid in member_ids
    }
    claimed: dict[str, str] = {}  # sector -> agent_id that keeps it

    # Process in a stable order; closest agent to a contested sector keeps it.
    def dist_to_sector(aid: str, sector: str) -> float:
        if aid not in positions:
            return float("inf")
        clat, clon = sector_center(bounds, sector)
        alat, alon = positions[aid]
        return haversine_km(alat, alon, clat, clon)

    # First pass: collect sector claims
    sector_claims: dict[str, list[str]] = {}
    for aid in member_ids:
        a = result.get(aid) or {}
        if (a.get("kind") or "") == "patrol_sector":
            sec = str(a.get("sector", "")).upper()
            if sec in SECTORS:
                sector_claims.setdefault(sec, []).append(aid)

    losers: list[str] = []
    for sec, claimers in sector_claims.items():
        winner = min(claimers, key=lambda x: dist_to_sector(x, sec))
        claimed[sec] = winner
        losers.extend(a for a in claimers if a != winner)

    # Reassign losers (and unassigned members) to the nearest free sector
    free = [s for s in SECTORS if s not in claimed]
    for aid in sorted(losers):
        if not free:
            free = ["CENTER"]
        best = min(free, key=lambda s: dist_to_sector(aid, s))
        result[aid] = {"kind": "patrol_sector", "sector": best}
        claimed[best] = aid
        if best in free:
            free.remove(best)

    # Any member with no assignment at all → nearest free sector / CENTER
    for aid in member_ids:
        if not result.get(aid):
            cand = free or ["CENTER"]
            best = min(cand, key=lambda s: dist_to_sector(aid, s))
            result[aid] = {"kind": "patrol_sector", "sector": best}
            if best in free:
                free.remove(best)

    return result
