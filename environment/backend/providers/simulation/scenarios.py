"""Selectable mission scenarios for the simulated world.

Each scenario reconfigures the world (contacts, points of interest, operating
area) and supplies the natural-language mission the human gives the lead asset.
Two are bespoke (a fully randomised open-sea picture and a structured
patrol-and-intercept), the other four are the challenge's reference missions.

``build_scenario(id)`` returns a dict the provider applies:
    {contacts, pois, mission, aor (GeoJSON polygon | None)}
"""

from __future__ import annotations

import random

from models.agent import Position
from models.world import Contact, POI

# Operating area (Strait of Sicily demo box) — kept consistent with sim_provider.
_LAT_MIN, _LAT_MAX = 37.42, 37.60
_LON_MIN, _LON_MAX = 15.00, 15.28

_COMMERCIAL = "AIS_COMMERCIAL"
_FISHING = "AIS_FISHING"
_UNKNOWN = "UNKNOWN"

# Scenario catalogue shown in the picker. `id` is the API key.
SCENARIOS = [
    {"id": "random", "name": "Random — Open Sea",
     "tag": "RANDOM",
     "blurb": "Randomised contacts and unknown/hostile vessels scattered across open sea.",
     "mission": "Patrol the area, identify any unknown or unflagged contact, and report anything suspicious."},
    {"id": "war", "name": "Patrol & Intercept",
     "tag": "TACTICAL",
     "blurb": "Structured tactical picture: commercial traffic plus intruders to intercept.",
     "mission": "Maintain a patrol line across the strait. Detect, intercept and shadow any "
                "unflagged or non-commercial contact penetrating the area."},
    {"id": "A", "name": "A — Patrol & Anomaly Report",
     "tag": "REFERENCE A",
     "blurb": "Patrol the marked area; flag any vessel that does not match a commercial AIS pattern.",
     "mission": "Patrol the marked area and report any vessel that does not match a commercial AIS pattern."},
    {"id": "B", "name": "B — Search with Priority",
     "tag": "REFERENCE B",
     "blurb": "Find the missing buoy in this region, prioritise speed.",
     "mission": "Find the missing buoy in this region, prioritise speed."},
    {"id": "C", "name": "C — Escort & Formation",
     "tag": "REFERENCE C",
     "blurb": "Escort the marked vessel, holding a 500 m loose formation.",
     "mission": "Escort the marked vessel for 30 minutes, maintain a 500 m loose formation."},
    {"id": "D", "name": "D — Sequential Investigation",
     "tag": "REFERENCE D",
     "blurb": "Investigate three points of interest in order, then converge on the rendezvous.",
     "mission": "Investigate the three points of interest in order (POI Alpha, POI Bravo, POI Charlie), "
                "then converge on the rendezvous point."},
]

_BY_ID = {s["id"]: s for s in SCENARIOS}


def list_scenarios() -> list[dict]:
    return SCENARIOS


def _rand_pos() -> Position:
    return Position(lat=round(random.uniform(_LAT_MIN, _LAT_MAX), 4),
                    lon=round(random.uniform(_LON_MIN, _LON_MAX), 4))


def _aor_polygon() -> dict:
    """A 'marked area' GeoJSON polygon covering the inner two-thirds of the box."""
    lat0, lat1 = _LAT_MIN + 0.03, _LAT_MAX - 0.03
    lon0, lon1 = _LON_MIN + 0.03, _LON_MAX - 0.03
    return {"type": "Polygon", "coordinates": [[
        [lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]]}


def _hdg() -> float:
    return round(random.uniform(0, 360), 0)


def _commercial(i: int, speed: tuple[float, float] = (8, 16)) -> Contact:
    """A randomly-placed conforming commercial AIS contact."""
    return Contact(id=f"c{i:03d}", position=_rand_pos(), heading=_hdg(),
                   speed_kn=round(random.uniform(*speed)),
                   label=_COMMERCIAL, mmsi=f"2471234{random.randint(10, 99)}")


def _fishing(i: int) -> Contact:
    return Contact(id=f"c{i:03d}", position=_rand_pos(), heading=_hdg(),
                   speed_kn=round(random.uniform(3, 9)),
                   label=_FISHING, mmsi=f"2471235{random.randint(10, 99)}")


def _unknown(i: int) -> Contact:
    """A randomly-placed anomaly: unknown / unflagged / non-conforming."""
    return Contact(id=f"c{i:03d}", position=_rand_pos(), heading=_hdg(),
                   speed_kn=round(random.uniform(10, 26)),
                   label=_UNKNOWN, flagged=random.random() < 0.7)


def build_scenario(scenario_id: str) -> dict:
    """Build a FRESH, randomised world for the scenario every call.

    Positions, counts, headings and speeds are all randomised so the swarm has
    to genuinely solve the scenario class — it can never memorise a fixed layout.
    Only the semantic structure (what kinds of objects exist, the mission intent)
    is fixed per scenario.
    """
    meta = _BY_ID.get(scenario_id) or _BY_ID["random"]
    sid = meta["id"]
    contacts: list[Contact] = []
    pois: list[POI] = []
    aor: dict | None = None
    i = 1  # running contact id counter

    if sid == "random":
        for _ in range(random.randint(5, 9)):
            r = random.random()
            contacts.append(_unknown(i) if r < 0.35 else (_fishing(i) if r < 0.6 else _commercial(i)))
            i += 1

    elif sid == "war":
        for _ in range(random.randint(4, 6)):       # commercial traffic
            contacts.append(_commercial(i)); i += 1
        for _ in range(random.randint(2, 3)):       # intruders to intercept
            contacts.append(_unknown(i)); i += 1
        aor = _aor_polygon()

    elif sid == "A":
        for _ in range(random.randint(3, 5)):       # conforming commercial
            contacts.append(_commercial(i)); i += 1
        for _ in range(random.randint(1, 3)):       # anomalies to flag
            contacts.append(random.choice([_unknown, _fishing])(i)); i += 1
        aor = _aor_polygon()

    elif sid == "B":
        # SEARCH: the buoy is a HIDDEN, stationary contact — NOT a briefed POI.
        # The agents are told only "find the missing buoy"; they must sweep the
        # area and DISCOVER it with their sensors (fog of war), exactly like any
        # other contact. Random clutter makes the search non-trivial.
        contacts.append(Contact(id="buoy", position=_rand_pos(), heading=0.0,
                                speed_kn=0.0, label="BUOY"))
        for _ in range(random.randint(2, 4)):
            contacts.append(_commercial(i)); i += 1
        aor = _aor_polygon()

    elif sid == "C":
        # A friendly vessel to escort (random track) plus random background traffic.
        contacts.append(Contact(id="escortee", position=_rand_pos(), heading=_hdg(),
                                speed_kn=round(random.uniform(8, 14)),
                                label=_COMMERCIAL, mmsi="247000999"))
        for _ in range(random.randint(2, 4)):
            contacts.append(random.choice([_commercial, _commercial, _unknown])(i)); i += 1

    elif sid == "D":
        # Three investigation POIs (random spots) + a random rendezvous.
        labels = ["POI Alpha", "POI Bravo", "POI Charlie"]
        pois = [POI(id=f"poi_{k+1}", position=_rand_pos(), label=labels[k]) for k in range(3)]
        pois.append(POI(id="rendezvous", position=_rand_pos(), label="Rendezvous"))
        for _ in range(random.randint(1, 3)):
            contacts.append(_commercial(i)); i += 1

    return {"contacts": contacts, "pois": pois, "mission": meta["mission"], "aor": aor}
