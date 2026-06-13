"""Swarm controller: wire LLM brains to the world model and run them.

Responsibilities:
  1. Reset the world and set the mission (REST).
  2. Read the scenario (operating area + POIs) once (REST).
  3. Spawn one :class:`AgentBrain` per world-model agent and run them together.

Keeps zero knowledge of the simulator internals — everything goes through the
world model's HTTP + WebSocket contract.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import requests

from maritime_swarm.ai_control.brain import AgentBrain
from maritime_swarm.ai_control.navigation_tools import default_registry
from maritime_swarm.ai_control.planner import GroqPlanner, HeuristicPlanner, Planner
from maritime_swarm.ai_control.scene import Scene
from maritime_swarm.ai_control.tools import ToolContext
from maritime_swarm.ai_control.world_client import WorldModelClient

logger = logging.getLogger(__name__)

DEFAULT_MISSION = (
    "PATROL ORDER: Maintain persistent surveillance of the assigned operating area in the "
    "Strait of Sicily. Detect, approach and identify any UNKNOWN or unflagged surface contacts. "
    "Keep the three assets dispersed for maximum sensor coverage and shadow anything suspicious."
)

# Cruise speeds (knots) used by the tools when transiting.
_CRUISE_BY_TYPE = {"USV": 28.0, "UAV": 80.0}


def _cruise_for(agent_type: str) -> float:
    return _CRUISE_BY_TYPE.get(agent_type.upper(), 25.0)


def _prepare_world(http_url: str, mission: str) -> dict[str, Any]:
    """Reset, set mission, and return the initial world state."""
    requests.post(f"{http_url}/api/reset", timeout=10).raise_for_status()
    requests.post(f"{http_url}/api/mission", json={"text": mission}, timeout=10).raise_for_status()
    resp = requests.get(f"{http_url}/api/state", timeout=10)
    resp.raise_for_status()
    return resp.json()


async def run_swarm(
    http_url: str,
    ws_url: str,
    mission: str,
    planner: Planner,
    min_think_interval: float = 4.0,
) -> None:
    """Run the full AI-controlled swarm until cancelled."""
    state = await asyncio.to_thread(_prepare_world, http_url, mission)
    scene = Scene.from_world_state(state)
    registry = default_registry()

    agents = state.get("agents", [])
    logger.info(
        "Controlling %d agents | planner=%s | area lat %.3f..%.3f lon %.3f..%.3f",
        len(agents),
        type(planner).__name__,
        scene.bounds.lat_min,
        scene.bounds.lat_max,
        scene.bounds.lon_min,
        scene.bounds.lon_max,
    )

    brains: list[AgentBrain] = []
    for a in agents:
        agent_type = str(a.get("type", "USV")).upper()
        ctx = ToolContext(
            agent_id=a["id"],
            agent_name=a.get("name", a["id"]),
            agent_type=agent_type,
            cruise_speed_kn=_cruise_for(agent_type),
            arrival_km=0.3,
            bounds=scene.bounds,
        )
        client = WorldModelClient(ws_url, a["id"])
        brains.append(
            AgentBrain(client, ctx, planner, scene, mission, registry, min_think_interval)
        )

    await asyncio.gather(*(b.run() for b in brains))


def build_planner(api_key: str | None, model: str, force_fake: bool = False) -> Planner:
    """Choose the real LLM planner when a key is available, else the fallback."""
    if api_key and not force_fake:
        logger.info("Using GroqPlanner (real LLM, model=%s)", model)
        return GroqPlanner(api_key=api_key, model=model)
    logger.warning(
        "No API key (or FAKE_LLM set) — using HeuristicPlanner. "
        "Set GROQ_API_KEY for real LLM decisions."
    )
    return HeuristicPlanner()
