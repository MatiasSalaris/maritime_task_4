from __future__ import annotations
from models.world import Contact
from models.agent import Position


def initial_contacts() -> list[Contact]:
    """Single missing-buoy target for the search mission."""
    return [
        Contact(
            id="buoy_01",
            position=Position(lat=37.545, lon=15.245),
            heading=0,
            speed_kn=0,
            label="BUOY",
        ),
    ]
