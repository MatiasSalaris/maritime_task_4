"""Decision planners: turn a situation into a tool call.

A planner is asked ``decide(obs, ctx, scene, mission, registry)`` and returns a
decision dict ``{"reasoning", "tool", "args"}``.

- :class:`GroqPlanner` calls a real LLM (Groq, via the shared ``groq_client``)
  in JSON mode. This is the default path — real AI choosing tools.
- :class:`HeuristicPlanner` is a deterministic, no-network fallback so the full
  loop (and the tests) run without an API key. It is NOT used when a key is set.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from maritime_swarm.ai_control.geo import haversine_km
from maritime_swarm.ai_control.observation import Observation
from maritime_swarm.ai_control.prompts import build_system_prompt, build_user_prompt
from maritime_swarm.ai_control.scene import Scene
from maritime_swarm.ai_control.tools import ToolContext, ToolRegistry
from maritime_swarm.llm.groq_client import inferenza_json

logger = logging.getLogger(__name__)


class Planner(Protocol):
    def decide(
        self,
        obs: Observation,
        ctx: ToolContext,
        scene: Scene,
        mission: str,
        registry: ToolRegistry,
    ) -> dict[str, Any]:
        ...


def _normalise_decision(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce an LLM response into the canonical decision shape."""
    tool = raw.get("tool") or raw.get("name") or raw.get("action")
    args = raw.get("args") or raw.get("arguments") or raw.get("parameters") or {}
    if not isinstance(args, dict):
        args = {}
    reasoning = str(raw.get("reasoning") or raw.get("thought") or "").strip()
    return {"reasoning": reasoning, "tool": tool, "args": args}


class GroqPlanner:
    """Real-LLM planner using the Groq OpenAI-compatible endpoint (JSON mode)."""

    def __init__(self, api_key: str, model: str, temperature: float = 0.3) -> None:
        self.api_key = api_key
        self.model = model
        self.temperature = temperature

    def decide(
        self,
        obs: Observation,
        ctx: ToolContext,
        scene: Scene,
        mission: str,
        registry: ToolRegistry,
    ) -> dict[str, Any]:
        system_prompt = build_system_prompt(registry)
        user_prompt = build_user_prompt(obs, ctx, scene, mission)
        raw = inferenza_json(
            prompt=user_prompt,
            api_key=self.api_key,
            system_prompt=system_prompt,
            model=self.model,
            temperature=self.temperature,
        )
        return _normalise_decision(raw)


class HeuristicPlanner:
    """Deterministic fallback planner (no LLM): investigate, else patrol.

    Used only when no API key is configured, so the simulation still moves and
    the loop can be exercised offline / in tests.
    """

    def __init__(self) -> None:
        self._patrol_idx: dict[str, int] = {}

    def decide(
        self,
        obs: Observation,
        ctx: ToolContext,
        scene: Scene,
        mission: str,
        registry: ToolRegistry,
    ) -> dict[str, Any]:
        # 1) Investigate the nearest suspicious contact, if any.
        suspicious = [c for c in obs.contacts if c.is_suspicious]
        if suspicious:
            nearest = min(suspicious, key=lambda c: haversine_km(obs.lat, obs.lon, c.lat, c.lon))
            return {
                "reasoning": f"Suspicious {nearest.label} contact {nearest.id} in range; closing to identify.",
                "tool": "investigate_contact",
                "args": {"contact_id": nearest.id},
            }

        # 2) Otherwise patrol toward the next point of interest / area corner.
        waypoints = self._patrol_waypoints(scene)
        idx = self._patrol_idx.get(ctx.agent_id, _seed_index(ctx.agent_id, len(waypoints)))
        lat, lon = waypoints[idx % len(waypoints)]
        self._patrol_idx[ctx.agent_id] = idx + 1
        return {
            "reasoning": "No contacts of interest; patrolling toward the next coverage waypoint.",
            "tool": "go_to",
            "args": {"lat": lat, "lon": lon},
        }

    @staticmethod
    def _patrol_waypoints(scene: Scene) -> list[tuple[float, float]]:
        if scene.pois:
            return [(p.lat, p.lon) for p in scene.pois]
        b = scene.bounds
        return [
            (b.lat_min, b.lon_min),
            (b.lat_max, b.lon_min),
            (b.lat_max, b.lon_max),
            (b.lat_min, b.lon_max),
        ]


def _seed_index(agent_id: str, n: int) -> int:
    """Stable per-agent starting offset so the three assets spread out."""
    return (sum(ord(ch) for ch in agent_id)) % max(1, n)
