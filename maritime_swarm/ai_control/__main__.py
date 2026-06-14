"""Run the AI-controlled maritime swarm against a running world model.

Usage (world model must be running, e.g. via environment/docker-compose):

    export GROQ_API_KEY=sk-...            # real LLM decisions
    python -m maritime_swarm.ai_control

Environment variables:
    OPENAI_API_KEY           OpenAI key — if set, uses OpenAI (default gpt-4o-mini)
    GROQ_API_KEY / API_KEY   Groq key (used when no OPENAI_API_KEY); omit all to
                             run the offline heuristic planner
    OPENAI_MODEL / GROQ_MODEL  model name override
    LLM_BASE_URL             OpenAI-compatible endpoint override (auto-set per provider)
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

from maritime_swarm.ai_control.controller import build_decider, run_swarm

# Default to a fast, high-rate-limit model so 3 agents stay responsive on a
# free-tier key. For maximum open-ended reasoning set GROQ_MODEL to a larger
# model (e.g. llama-3.3-70b-versatile) if your key's rate limits allow it.
_DEFAULT_MODEL = "llama-3.1-8b-instant"
from maritime_swarm.infrastructure.environment_config import load_dotenv


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
    force_fake = _clean(os.getenv("FAKE_LLM"), "0").lower() in ("1", "true", "yes")
    # Strip surrounding quotes/whitespace: Docker Compose env_file passes values
    # literally (a quoted .env value would otherwise carry the quotes through).
    # Provider selection: an OPENAI_API_KEY switches the whole stack to OpenAI
    # (and points the OpenAI-compatible client at OpenAI's endpoint); otherwise
    # fall back to Groq via GROQ_API_KEY / API_KEY.
    openai_key = _clean(os.getenv("OPENAI_API_KEY")) or None
    groq_key = _clean(os.getenv("GROQ_API_KEY") or os.getenv("API_KEY")) or None
    if openai_key:
        api_key = openai_key
        if not _clean(os.getenv("LLM_BASE_URL") or os.getenv("GROQ_BASE_URL")):
            os.environ["LLM_BASE_URL"] = "https://api.openai.com/v1"
        model = _clean(os.getenv("OPENAI_MODEL") or os.getenv("GROQ_MODEL")) or "gpt-4o-mini"
    else:
        api_key = groq_key
        model = _clean(os.getenv("GROQ_MODEL")) or _DEFAULT_MODEL

    decider = build_decider(api_key, model, force_fake=force_fake)

    try:
        asyncio.run(run_swarm(http_url, ws_url, mission, decider))
    except KeyboardInterrupt:
        print("\nShutting down AI control.")


if __name__ == "__main__":
    main()
