#!/usr/bin/env python3
"""Entrypoint for the maritime swarm demo simulation."""

from __future__ import annotations

import asyncio
import os

from maritime_swarm.agent_runtime.maritime_agent import MaritimeAgent
from maritime_swarm.communication.async_event_bus import EventBus
from maritime_swarm.demo.demo_logger import DemoLogger
from maritime_swarm.demo.demo_scenario import run_demo
from maritime_swarm.domain.spawn_positions import random_spawn_positions
from maritime_swarm.infrastructure.environment_config import configured_model, load_dotenv, require_api_key
from maritime_swarm.llm.real_llm_service import LLMService


def build_agents(
    bus: EventBus,
    llm: LLMService,
    logger: DemoLogger,
    positions: dict[str, tuple[float, float]],
) -> dict[str, MaritimeAgent]:
    """Create the three maritime assets with generated spawn positions."""
    return {
        "USV-1": MaritimeAgent("USV-1", bus, positions["USV-1"], 72.0, 0.82, llm, logger),
        "USV-2": MaritimeAgent("USV-2", bus, positions["USV-2"], 91.0, 0.74, llm, logger),
        "USV-3": MaritimeAgent("USV-3", bus, positions["USV-3"], 64.0, 0.95, llm, logger),
    }


async def main() -> None:
    """Load config, build dependencies, and run the scripted demo."""
    load_dotenv()
    api_key = require_api_key()
    model = configured_model()
    seed_text = os.getenv("SPAWN_SEED")
    seed = int(seed_text) if seed_text else None
    logger = DemoLogger()
    positions = random_spawn_positions(seed)
    bus = EventBus(logger)
    llm = LLMService(api_key, model)
    agents = build_agents(bus, llm, logger, positions)

    logger.log("SIM", f"starting deterministic shared-situational-picture swarm with real LLM model={model}")
    logger.log("SIM", f"spawn_positions={positions} seed={seed if seed is not None else 'random'}")
    logger.log("SIM", f"log_file={logger.file_path}")
    await run_demo(bus, agents, logger)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("interrupted")
