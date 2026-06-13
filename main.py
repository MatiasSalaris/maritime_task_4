"""Entrypoint: build the world, create the three agents and the bus, run the loop.

This module wires the pieces together and drives the simulation. It does NOT
assign tasks — coordination must emerge peer-to-peer through the bus.

Skeleton only: the loop is TODO.
"""

import os

from swarm import Agent
# from swarm import World   # owned separately

API_KEY = os.getenv("API_KEY")


PROMPT_MISSIONE = """\
    We've lost contact with navigation buoy NB-7 somewhere in the northern survey sector.
    It's a standard yellow special-mark buoy, last reported roughly in the centre of the area before it stopped transmitting, so it has likely drifted from that position.
    Take the swarm in and find it. Speed is the priority here.
    I need it located as fast as possible, so cover the area quickly rather than exhaustively.
    Report the moment any agent gets a positive visual identification, with its position.
"""


def build_agents() -> list[Agent]:
    """Create the three assets. The first is the LEAD."""
    raise NotImplementedError  # TODO


def run(mission: str) -> None:
    """Main loop: perceive -> reason -> message -> deliver -> step -> render."""
    raise NotImplementedError  # TODO


if __name__ == "__main__":
    run(PROMPT_MISSIONE)
