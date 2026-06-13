"""Readable state summaries for demo logs."""

from __future__ import annotations


def log_state_tiers(agent) -> None:
    """Log a compact summary of the agent's three state tiers."""
    agent.logger.log(
        agent.id,
        "STATE_TIERS physical={physical}; cognitive={cognitive}; distributed={distributed}".format(
            physical={
                "pos": agent.state.physical_state["pos"],
                "battery": agent.state.physical_state["battery"],
                "sensor_quality": agent.state.physical_state["sensor_quality"],
                "raw_contacts": [],
            },
            cognitive={
                "local_beliefs": {},
                "local_intent": agent.state.cognitive_state["local_intent"],
            },
            distributed={"mission_intent": None, "shared_contacts": {}, "global_tasks": {}},
        ),
    )
