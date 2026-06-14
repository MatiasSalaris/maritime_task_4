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
        self.time_scale = 1.0  # sim-time multiplier; 2.0 = world runs 2x faster
        self.paused = False    # when True: world frozen + no observations to agents

    async def run(self) -> None:
        self._running = True
        interval = 1.0 / settings.tick_rate
        logger.info("Engine started at %d Hz", settings.tick_rate)

        while self._running:
            t0 = time.monotonic()

            # When paused (e.g. after a reset), freeze the world and withhold
            # observations so the AI agents stop thinking/acting entirely. We
            # still broadcast the (static) world state so the frontend stays
            # live. Issuing a new mission un-pauses the engine.
            if not self.paused:
                # Advance simulation (no-op for hardware provider). The wall-clock
                # tick rate stays fixed; time_scale stretches/shrinks how much
                # sim-time each tick advances, so the world runs faster or slower.
                await self.provider.tick(interval * self.time_scale)

            # Expire old in-flight messages
            message_bus.expire_in_flight(3.0, time.time())

            # Build world state snapshot
            state = await self.provider.get_world_state()
            payload = state.model_dump()
            payload["messages_in_flight"] = message_bus.in_flight_dicts()
            payload["message_log"] = message_bus.log_dicts()

            # Push to all frontend connections
            await manager.broadcast({"type": "world_state", "payload": payload})

            # Push observations to each connected LLM agent (skipped while paused)
            if not self.paused:
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
