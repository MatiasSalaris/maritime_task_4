"""Swarm controller: wire LLM brains to the world model and run them.

Responsibilities:
  1. Reset the world and read any explicit mission (REST).
  2. Read the scenario (operating area + POIs) once (REST).
  3. Spawn one :class:`AgentBrain` per world-model agent and run them together.

Keeps zero knowledge of the simulator internals — everything goes through the
world model's HTTP + WebSocket contract.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import requests

from maritime_swarm.ai_control.brain import AgentBrain
from maritime_swarm.ai_control.navigation_tools import default_registry
from maritime_swarm.ai_control.planner import AgentDecider, GroqDecider, HeuristicDecider
from maritime_swarm.ai_control.rate_limit import NullLimiter, RateLimiter
from maritime_swarm.ai_control.scene import Scene
from maritime_swarm.ai_control.tools import ToolContext
from maritime_swarm.ai_control.world_client import WorldModelClient

logger = logging.getLogger(__name__)

_DEMO_CRUISE_KN = 10_000.0

# Cruise speeds (knots) used by the tools when transiting. These are deliberately
# inflated by five orders of magnitude for fast simulation iteration.
_CRUISE_BY_TYPE = {"USV": _DEMO_CRUISE_KN, "UAV": _DEMO_CRUISE_KN}


def _cruise_for(agent_type: str) -> float:
    return _CRUISE_BY_TYPE.get(agent_type.upper(), _DEMO_CRUISE_KN)


def _wait_for_backend(http_url: str, timeout_s: float = 120.0) -> None:
    """Block until the world model answers /health (it may still be booting)."""
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            requests.get(f"{http_url}/health", timeout=5).raise_for_status()
            return
        except Exception as exc:  # not up yet
            if time.monotonic() >= deadline:
                raise RuntimeError(f"world model at {http_url} did not become healthy") from exc
            logger.info("Waiting for world model at %s ...", http_url)
            time.sleep(2.0)


def _prepare_world(http_url: str, mission_override: str | None) -> tuple[dict[str, Any], str | None]:
    """Reset the world and return (initial world state, optional mission).

    Mission precedence (so a mission typed in the frontend is respected):
        explicit override  >  mission already set in the world  >  no mission.
    The current mission is read *before* the reset (which clears it).
    """
    _wait_for_backend(http_url)
    pre = requests.get(f"{http_url}/api/state", timeout=10)
    pre.raise_for_status()
    existing = (pre.json().get("mission") or "").strip()

    mission = (mission_override or "").strip() or existing or None

    requests.post(f"{http_url}/api/reset", timeout=10).raise_for_status()
    if mission:
        requests.post(f"{http_url}/api/mission", json={"text": mission}, timeout=10).raise_for_status()

    resp = requests.get(f"{http_url}/api/state", timeout=10)
    resp.raise_for_status()
    return resp.json(), mission


async def run_swarm(
    http_url: str,
    ws_url: str,
    mission: str | None,
    decider: AgentDecider,
) -> None:
    """Run the full AI-controlled swarm until cancelled.

    ``mission`` may be ``None`` to adopt whatever mission is already set in the
    world model (e.g. typed in the frontend).
    """
    state, mission = await asyncio.to_thread(_prepare_world, http_url, mission)
    scene = Scene.from_world_state(state)
    if mission:
        logger.info("Mission: %s", mission)
    else:
        logger.info("No mission set — agents are idle until a mission is submitted.")
    registry = default_registry()

    agents = state.get("agents", [])
    # One shared limiter paces all agents' LLM calls under the provider's TPM
    # limit (real LLM only; the heuristic decider needs no pacing).
    from maritime_swarm.llm.groq_client import last_remaining_tokens
    limiter = RateLimiter(budget_fn=last_remaining_tokens) if isinstance(decider, GroqDecider) else NullLimiter()
    logger.info(
        "Controlling %d agents | decider=%s | area lat %.3f..%.3f lon %.3f..%.3f",
        len(agents), type(decider).__name__,
        scene.bounds.lat_min, scene.bounds.lat_max, scene.bounds.lon_min, scene.bounds.lon_max,
    )

    brains: list[AgentBrain] = []
    for a in agents:
        agent_type = str(a.get("type", "USV")).upper()
        sensor_km = float(a.get("sensor_range_km") or 4.0)
        ctx = ToolContext(
            agent_id=a["id"],
            agent_name=a.get("name", a["id"]),
            agent_type=agent_type,
            cruise_speed_kn=_cruise_for(agent_type),
            sensor_range_km=sensor_km,
            arrival_km=0.3,
            identify_km=max(0.8, 0.75 * sensor_km),
            bounds=scene.bounds,
        )
        client = WorldModelClient(ws_url, a["id"])
        brains.append(AgentBrain(client, ctx, decider, scene, mission, registry, limiter=limiter))

    await asyncio.gather(*(b.run() for b in brains))


def build_decider(api_key: str | None, model: str, force_fake: bool = False) -> AgentDecider:
    """The real LLM decider when a key is available, else the offline fallback."""
    if api_key and not force_fake:
        from maritime_swarm.llm.groq_client import _base_url
        logger.info("Using real LLM | endpoint=%s model=%s", _base_url(), model)
        return GroqDecider(api_key=api_key, model=model)
    logger.warning(
        "No API key (or FAKE_LLM set) — using the offline HeuristicDecider. "
        "Set GROQ_API_KEY for real open-ended LLM coordination."
    )
    return HeuristicDecider()
