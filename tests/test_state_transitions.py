"""Tests for mission success and obstacle state transitions."""

import unittest

from maritime_swarm.agent_runtime.maritime_agent import MaritimeAgent
from maritime_swarm.agent_runtime.swarm_event_handlers import on_buoy_detected
from maritime_swarm.domain.agent_state import AgentMode
from tests.fakes import FakeBus, FakeLLM, FakeLogger


def make_agent(agent_id: str = "USV-1") -> MaritimeAgent:
    """Create one agent with fake dependencies."""
    return MaritimeAgent(agent_id, FakeBus(), (10, 20), 80, 0.8, FakeLLM(), FakeLogger())


class StateTransitionTests(unittest.TestCase):
    """Verify important state-machine transitions."""

    def test_buoy_detection_completes_mission(self) -> None:
        agent = make_agent()
        agent.state.distributed_state["mission_intent"] = {"mission_id": "M-001", "status": "accepted"}
        agent.state.distributed_state["global_tasks"]["search"] = {"status": "assigned"}
        agent.state.state = AgentMode.EXECUTING
        agent.state.active_task = "search"

        on_buoy_detected(agent, {"contact_id": "C17", "detected_by": "USV-3", "contact_pos": (58, 72)})

        self.assertEqual(agent.state.state, AgentMode.IDLE)
        self.assertIsNone(agent.state.active_task)
        self.assertEqual(agent.state.distributed_state["mission_intent"]["status"], "complete")
        self.assertEqual(agent.state.distributed_state["global_tasks"]["search"]["status"], "closed_by_success")


if __name__ == "__main__":
    unittest.main()
