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

from maritime_swarm.ai_control.controller import build_planner, run_swarm
from maritime_swarm.infrastructure.environment_config import configured_model, load_dotenv


def _clean(value: str | None, default: str = "") -> str:
    """Return an env value with surrounding whitespace and quotes removed."""
    if value is None:
        return default
    return value.strip().strip('"').strip("'").strip()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s", datefmt="%H:%M:%S")
    load_dotenv()

    http_url = _clean(os.getenv("WORLD_HTTP_URL"), "http://localhost:8000").rstrip("/")
    ws_url = _clean(os.getenv("WORLD_WS_URL"), "ws://localhost:8000").rstrip("/")
    # No MISSION env → adopt whatever mission is set in the world (e.g. typed
    # in the frontend); the controller falls back to the default if none.
    mission = _clean(os.getenv("MISSION")) or None
    think_interval = float(_clean(os.getenv("THINK_INTERVAL"), "4"))
    force_fake = _clean(os.getenv("FAKE_LLM"), "0").lower() in ("1", "true", "yes")
    # Strip surrounding quotes/whitespace: Docker Compose env_file passes values
    # literally (a quoted .env value would otherwise carry the quotes through).
    api_key = _clean(os.getenv("GROQ_API_KEY") or os.getenv("API_KEY")) or None
    model = _clean(os.getenv("GROQ_MODEL")) or configured_model()

    planner = build_planner(api_key, model, force_fake=force_fake)

    try:
        asyncio.run(run_swarm(http_url, ws_url, mission, planner, think_interval))
    except KeyboardInterrupt:
        print("\nShutting down AI control.")


if __name__ == "__main__":
    main()
