"""Test doubles for bus, logger, and LLM dependencies."""

from __future__ import annotations


class FakeLogger:
    """Collect log messages without writing files."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def log(self, tag: str, message: str) -> None:
        """Store one log event."""
        self.events.append((tag, message))


class FakeBus:
    """Collect published events for assertions."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    async def publish(self, event: dict) -> None:
        """Store one event."""
        self.events.append(event)

    async def subscribe(self, subscriber_id: str):
        """Return a placeholder inbox."""
        raise NotImplementedError

    async def unsubscribe(self, subscriber_id: str) -> None:
        """No-op in tests."""


class FakeLLM:
    """Return deterministic text for LLM-dependent methods."""

    model = "fake-model"

    async def parse_mission(self, mission: str) -> dict:
        """Return a stable parsed mission."""
        return {
            "objective": "locate missing buoy",
            "constraints": ["stop once detected"],
            "priority": "speed",
            "local_intent": "search quickly",
        }

    async def decision_trace(self, prompt: str) -> str:
        """Return a stable trace."""
        return f"trace: {prompt.splitlines()[0]}"
