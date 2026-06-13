from __future__ import annotations
import asyncio
import logging
import time
from config import settings
from engine.connection_manager import manager
from engine.message_bus import message_bus
from providers.base import AbstractPlatformProvider

logger = logging.getLogger(__name__)


class WorldStateEngine:
    def __init__(self, provider: AbstractPlatformProvider) -> None:
        self.provider = provider
        self._running = False

    async def run(self) -> None:
        self._running = True
        interval = 1.0 / settings.tick_rate
        logger.info("Engine started at %d Hz", settings.tick_rate)

        while self._running:
            t0 = time.monotonic()

            # Advance simulation (no-op for hardware provider)
            await self.provider.tick(interval)

            # Expire old in-flight messages
            message_bus.expire_in_flight(3.0, time.time())

            # Build world state snapshot
            state = await self.provider.get_world_state()
            payload = state.model_dump()
            payload["messages_in_flight"] = message_bus.in_flight_dicts()
            payload["message_log"] = message_bus.log_dicts()

            # Push to all frontend connections
            await manager.broadcast({"type": "world_state", "payload": payload})

            # Push observations to each connected LLM agent
            for agent_id in manager.connected_agent_ids():
                obs = await self.provider.get_observation(
                    agent_id, message_bus.drain_inbox(agent_id)
                )
                if obs:
                    await manager.send_to_agent(
                        agent_id, {"type": "observation", "payload": obs.model_dump()}
                    )

            elapsed = time.monotonic() - t0
            sleep = max(0.0, interval - elapsed)
            await asyncio.sleep(sleep)

    def stop(self) -> None:
        self._running = False
