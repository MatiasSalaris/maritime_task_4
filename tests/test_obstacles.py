"""Tests for local obstacle handling and handoff emission."""

import unittest

from maritime_swarm.agent_runtime.maritime_agent import MaritimeAgent
from maritime_swarm.domain.agent_state import AgentMode
from tests.fakes import FakeBus, FakeLLM, FakeLogger


class ObstacleTests(unittest.IsolatedAsyncioTestCase):
    """Verify obstacle handling behavior without peer validation."""

    async def test_north_blocked_emits_handoff_and_keeps_agent_executing(self) -> None:
        bus = FakeBus()
        agent = MaritimeAgent("USV-2", bus, (42, 36), 91, 0.74, FakeLLM(), FakeLogger())
        agent.state.state = AgentMode.EXECUTING
        agent.state.active_task = "search_north_sector"
        agent.state.distributed_state["global_tasks"]["search_north_sector"] = {
            "target_pos": (58, 72),
            "bids": {},
            "status": "assigned",
        }

        await agent.detect_obstacle("O9", (54, 52), blocks_direction="north")

        self.assertEqual(agent.state.state, AgentMode.EXECUTING)
        self.assertEqual(agent.state.active_task, "alternate_east_sweep")
        self.assertEqual(bus.events[-1]["type"], "HANDOFF_REQUEST")


if __name__ == "__main__":
    unittest.main()
