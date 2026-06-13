from __future__ import annotations
from models.world import Contact
from models.agent import Position


def initial_contacts() -> list[Contact]:
    """A handful of synthetic AIS contacts in the Strait of Sicily demo area."""
    return [
        Contact(
            id="c001",
            position=Position(lat=37.55, lon=15.21),
            heading=270, speed_kn=14,
            label="AIS_COMMERCIAL", mmsi="247123401",
        ),
        Contact(
            id="c002",
            position=Position(lat=37.44, lon=15.04),
            heading=90, speed_kn=5,
            label="AIS_FISHING", mmsi="247123402",
        ),
        Contact(
            id="c003",
            position=Position(lat=37.53, lon=15.13),
            heading=200, speed_kn=18,
            label="UNKNOWN", flagged=True,
        ),
        Contact(
            id="c004",
            position=Position(lat=37.57, lon=15.07),
            heading=45, speed_kn=10,
            label="AIS_COMMERCIAL", mmsi="247123404",
        ),
        Contact(
            id="c005",
            position=Position(lat=37.46, lon=15.19),
            heading=315, speed_kn=7,
            label="AIS_FISHING", mmsi="247123405",
        ),
    ]
