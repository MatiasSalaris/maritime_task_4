"""Run the AI-controlled maritime swarm against a running world model.

Usage (world model must be running, e.g. via environment/docker-compose):

    export GROQ_API_KEY=sk-...            # real LLM decisions
    python -m maritime_swarm.ai_control

Environment variables:
    GROQ_API_KEY / API_KEY   LLM key (omit to run the offline heuristic planner)
    GROQ_MODEL               model name (default llama-3.1-8b-instant)
    WORLD_HTTP_URL           default http://localhost:8000
    WORLD_WS_URL             default ws://localhost:8000
    MISSION                  override the default patrol mission text
    THINK_INTERVAL           min seconds between LLM calls per agent (default 4)
    FAKE_LLM                 set to 1 to force the heuristic planner
"""

from __future__ import annotations

import asyncio
import logging
import os

from maritime_swarm.ai_control.controller import DEFAULT_MISSION, build_planner, run_swarm
from maritime_swarm.infrastructure.environment_config import configured_model, load_dotenv


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s", datefmt="%H:%M:%S")
    load_dotenv()

    http_url = os.getenv("WORLD_HTTP_URL", "http://localhost:8000").rstrip("/")
    ws_url = os.getenv("WORLD_WS_URL", "ws://localhost:8000").rstrip("/")
    mission = os.getenv("MISSION", DEFAULT_MISSION)
    think_interval = float(os.getenv("THINK_INTERVAL", "4"))
    force_fake = os.getenv("FAKE_LLM", "0").lower() in ("1", "true", "yes")
    api_key = os.getenv("GROQ_API_KEY") or os.getenv("API_KEY")

    planner = build_planner(api_key, configured_model(), force_fake=force_fake)

    try:
        asyncio.run(run_swarm(http_url, ws_url, mission, planner, think_interval))
    except KeyboardInterrupt:
        print("\nShutting down AI control.")


if __name__ == "__main__":
    main()
