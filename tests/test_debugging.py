"""Tests for the debugging utilities and logger helpers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from maritime_swarm.agent_runtime.maritime_agent import MaritimeAgent
from maritime_swarm.debugging import capture_agent_state
from maritime_swarm.demo.demo_logger import DemoLogger
from tests.fakes import FakeBus, FakeLLM, FakeLogger


class DebuggingToolsTests(unittest.TestCase):
    """Verify that debugging helpers expose useful information."""

    def test_capture_agent_state_returns_recent_events_and_traces(self) -> None:
        agent = MaritimeAgent("USV-1", FakeBus(), (10.0, 5.0), 90.0, 0.85, FakeLLM(), FakeLogger())
        agent.state.local_event_log.extend([
            {"type": "TASK_TRIGGER", "task_id": "search", "timestamp": 123.456789},
            {"type": "TASK_BID", "task_id": "search", "timestamp": 124.123456},
        ])
        agent.state.cognitive_state["decision_traces"] = ["trace-a", "trace-b", "trace-c"]

        snapshot = capture_agent_state(agent, event={"type": "TEST_EVENT", "timestamp": 125.0}, limit_events=2, limit_traces=2)

        self.assertEqual(snapshot["agent_id"], "USV-1")
        self.assertEqual(snapshot["mode"], agent.state.state.value)
        self.assertEqual(len(snapshot["recent_events"]), 2)
        self.assertEqual(snapshot["recent_events"][-1]["type"], "TASK_BID")
        self.assertEqual(snapshot["decision_traces"], ["trace-b", "trace-c"])
        self.assertEqual(snapshot["trigger_event"]["type"], "TEST_EVENT")

    def test_demo_logger_writes_debug_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            logger = DemoLogger(log_dir=tmp_dir, debug_enabled=True)
            path = logger.log_debug("USV-1", "test snapshot", {"value": 42})

            self.assertIsNotNone(path)
            assert path is not None  # satisfy type checkers
            self.assertTrue(Path(path).is_file())
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            self.assertEqual(payload["value"], 42)


if __name__ == "__main__":
    unittest.main()
