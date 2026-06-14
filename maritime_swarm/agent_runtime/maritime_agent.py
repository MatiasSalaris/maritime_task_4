"""Autonomous maritime asset runtime and event dispatch loop."""

from __future__ import annotations

import asyncio
from typing import Any

from maritime_swarm.agent_runtime import operator_and_sensor_actions, swarm_event_handlers
from maritime_swarm.agent_runtime.handoff_handlers import on_handoff_request
from maritime_swarm.agent_runtime.state_tier_logging import log_state_tiers
from maritime_swarm.agent_runtime.task_execution_logic import AgentTaskLogic
from maritime_swarm.communication.async_event_bus import EventBus
from maritime_swarm.demo.demo_logger import DemoLogger
from maritime_swarm.domain.agent_state import AgentState, build_agent_state
from maritime_swarm.debugging import capture_agent_state
from maritime_swarm.llm.real_llm_service import LLMService


class MaritimeAgent(AgentTaskLogic):
    """One autonomous asset with local state and peer-to-peer event handlers."""

    BID_COLLECTION_SECONDS = 0.5

    def __init__(
        self,
        agent_id: str,
        bus: EventBus,
        pos: tuple[float, float],
        battery: float,
        sensor_quality: float,
        llm: LLMService,
        logger: DemoLogger,
    ) -> None:
        self.id = agent_id
        self.bus = bus
        self.llm = llm
        self.logger = logger
        self.inbox: asyncio.Queue[dict[str, Any]] | None = None
        self.state: AgentState = build_agent_state(pos, battery, sensor_quality)
        self._tasks: list[asyncio.Task[Any]] = []
        self._shutdown = asyncio.Event()
        self._debug_enabled = bool(getattr(logger, "debug_enabled", False))

    async def start(self) -> None:
        """Subscribe to the bus and start the event loop side effect."""
        self.inbox = await self.bus.subscribe(self.id)
        self._tasks.append(asyncio.create_task(self._listen_loop(), name=f"{self.id}:listener"))
        self.logger.log(self.id, "online")
        log_state_tiers(self)
        self._debug_snapshot("startup", None)

    async def shutdown(self) -> None:
        """Cancel internal tasks and unsubscribe from the bus."""
        self._shutdown.set()
        for task in self._tasks:
            if not task.done():
                task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        await self.bus.unsubscribe(self.id)
        self.logger.log(self.id, "shutdown complete")
        self._debug_snapshot("shutdown", None)

    async def receive_operator_mission(self, mission_id: str, mission: str, operator_pos: tuple[float, float]) -> None:
        """Receive NLP intent, parse it with the LLM, and broadcast briefing."""
        await operator_and_sensor_actions.receive_operator_mission(self, mission_id, mission, operator_pos)
        self._debug_snapshot("after_receive_operator_mission", {
            "type": "MISSION_RECEIVED",
            "mission_id": mission_id,
            "operator_pos": operator_pos,
        })

    async def detect_buoy(self, contact_id: str, contact_pos: tuple[float, float]) -> None:
        """Record a certain buoy detection and broadcast mission completion evidence."""
        await operator_and_sensor_actions.detect_buoy(self, contact_id, contact_pos)
        self._debug_snapshot("after_detect_buoy", {
            "type": "BUOY_DETECTED",
            "contact_id": contact_id,
            "contact_pos": contact_pos,
        })

    async def detect_obstacle(self, obstacle_id: str, obstacle_pos: tuple[float, float], blocks_direction: str | None = None) -> None:
        """Handle a local obstacle; side effects may include reroute or handoff."""
        await operator_and_sensor_actions.detect_obstacle(self, obstacle_id, obstacle_pos, blocks_direction)
        self._debug_snapshot("after_detect_obstacle", {
            "type": "OBSTACLE_DETECTED",
            "obstacle_id": obstacle_id,
            "obstacle_pos": obstacle_pos,
            "blocks_direction": blocks_direction,
        })

    async def _listen_loop(self) -> None:
        assert self.inbox is not None
        while not self._shutdown.is_set():
            event = await self.inbox.get()
            self.state.local_event_log.append(event)
            event_type = str(event.get("type", "event")).lower()
            self._debug_snapshot(f"before_{event_type}", event)
            await self._dispatch(event)
            self._debug_snapshot(f"after_{event_type}", event)

    async def _dispatch(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        if event_type == "MISSION_INTENT":
            swarm_event_handlers.on_mission_intent(self, event)
        elif event_type == "BUOY_DETECTED":
            swarm_event_handlers.on_buoy_detected(self, event)
        elif event_type == "TASK_TRIGGER":
            await swarm_event_handlers.on_task_trigger(self, event)
        elif event_type == "TASK_BID":
            swarm_event_handlers.on_task_bid(self, event)
        elif event_type == "HANDOFF_REQUEST":
            await on_handoff_request(self, event)

    def _debug_snapshot(self, label: str, event: dict[str, Any] | None) -> None:
        """Write a structured snapshot when debugging is enabled."""

        if not self._debug_enabled:
            return
        snapshot = capture_agent_state(self, event=event)
        debug_path = None
        if hasattr(self.logger, "log_debug"):
            debug_path = self.logger.log_debug(self.id, label, snapshot)
        if debug_path is not None:
            self.logger.log(self.id, f"DEBUG_SNAPSHOT {label} -> {debug_path.name}")
