"""Async in-memory peer-to-peer event bus used by all agents."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from maritime_swarm.communication.message_validation import validate_message
from maritime_swarm.demo.demo_logger import DemoLogger


class EventBus:
    """Broadcast JSON-like events to one queue per subscribed agent."""

    def __init__(self, logger: DemoLogger) -> None:
        self._logger = logger
        self._subscribers: dict[str, asyncio.Queue[dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, subscriber_id: str) -> asyncio.Queue[dict[str, Any]]:
        """Create an inbox for an agent; side effect: registers subscriber."""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        async with self._lock:
            self._subscribers[subscriber_id] = queue
        self._logger.log("BUS", f"{subscriber_id} subscribed")
        return queue

    async def unsubscribe(self, subscriber_id: str) -> None:
        """Remove an agent inbox; side effect: stops future deliveries."""
        async with self._lock:
            self._subscribers.pop(subscriber_id, None)
        self._logger.log("BUS", f"{subscriber_id} unsubscribed")

    async def publish(self, event: dict[str, Any]) -> None:
        """Validate, stamp, and broadcast an event to all subscribers."""
        validate_message(event)
        stamped = {
            **event,
            "event_id": event.get("event_id", f"evt-{time.monotonic_ns()}"),
            "timestamp": time.monotonic(),
        }
        async with self._lock:
            subscribers = list(self._subscribers.items())
        for _, queue in subscribers:
            await queue.put(stamped.copy())
        self._logger.log(
            "BUS",
            f"broadcast {stamped['type']} from {stamped.get('sender', 'SIM')} to {len(subscribers)} agents",
        )
