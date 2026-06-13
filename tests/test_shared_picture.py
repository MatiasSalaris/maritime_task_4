"""Tests for shared situational picture updates."""

import unittest

from maritime_swarm.agent_runtime.swarm_event_handlers import on_buoy_detected
from tests.test_state_transitions import make_agent


class SharedPictureTests(unittest.TestCase):
    """Verify direct buoy detection updates distributed contact state."""

    def test_single_buoy_detection_is_accepted_without_peer_vote(self) -> None:
        agent = make_agent("USV-2")
        event = {"contact_id": "C17", "detected_by": "USV-3", "contact_pos": (58, 72)}

        on_buoy_detected(agent, event)

        contact = agent.state.distributed_state["shared_contacts"]["C17"]
        self.assertEqual(contact["type"], "buoy")
        self.assertEqual(contact["detected_by"], "USV-3")
        self.assertEqual(contact["validation_policy"], "single asset detection is sufficient")


if __name__ == "__main__":
    unittest.main()
