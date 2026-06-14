"""Mission entrypoint rules: raw NLP goes only to the leader."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from maritime_swarm.communication.event_messages import mission_intent
from maritime_swarm.communication.message_validation import validate_message


def test_mission_intent_event_omits_raw_operator_text() -> None:
    raw = "Find the missing buoy in this region, prioritise speed."
    parsed = {
        "objective": "Locate the missing buoy",
        "priority": "Speed",
        "constraints": ["Report detection to peers"],
        "local_intent": "Search quickly and report detection.",
    }

    event = mission_intent("M-001", raw, parsed, "USV-1")

    validate_message(event)
    assert "nlp_mission" not in event
    assert raw not in repr(event)
    assert event["briefing"]["objective"] == parsed["objective"]


def test_sim_provider_sends_raw_mission_only_to_entry_agent() -> None:
    backend_path = Path(__file__).resolve().parents[1] / "environment" / "backend"
    sys.path.insert(0, str(backend_path))
    try:
        from providers.simulation.sim_provider import SimulatedPlatformProvider

        provider = SimulatedPlatformProvider()
        raw = "Find the missing buoy in this region, prioritise speed."
        asyncio.run(provider.set_mission(raw))

        leader_obs = asyncio.run(provider.get_observation("agent_0", []))
        peer_obs = asyncio.run(provider.get_observation("agent_1", []))

        assert leader_obs is not None and leader_obs.mission == raw
        assert peer_obs is not None and peer_obs.mission is None
        assert peer_obs.mission_status == "active"
    finally:
        try:
            sys.path.remove(str(backend_path))
        except ValueError:
            pass
