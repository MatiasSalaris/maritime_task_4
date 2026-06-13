"""Strategic planner: interpret the mission and propose a division of labour.

Run by the *leader* asset (the entry point for the human's mission). The output
is broadcast as a P2P proposal; peers may object. This is not a central planner
— it has no command authority, only the first word in a negotiation.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from maritime_swarm.ai_control.coordination import SECTORS, default_allocation
from maritime_swarm.ai_control.prompts import strategist_system_prompt, strategist_user_prompt
from maritime_swarm.ai_control.scene import Scene
from maritime_swarm.ai_control.tools import Bounds
from maritime_swarm.llm.groq_client import inferenza_json

logger = logging.getLogger(__name__)

_VALID_KINDS = {"patrol_sector", "investigate", "escort", "visit_pois", "rendezvous", "hold"}


class Strategist(Protocol):
    def plan(
        self, mission: str, members: list[dict[str, Any]], scene: Scene, contacts: list[dict[str, Any]]
    ) -> dict[str, Any]:
        ...


def _normalise_plan(raw: dict[str, Any], members: list[dict[str, Any]], bounds: Bounds) -> dict[str, Any]:
    member_ids = [m["id"] for m in members]
    brief = raw.get("brief") if isinstance(raw.get("brief"), dict) else {}
    brief = {
        "objective": str(brief.get("objective") or "").strip(),
        "constraints": [str(c) for c in (brief.get("constraints") or [])],
        "priority": brief.get("priority"),
    }
    raw_alloc = raw.get("allocation") if isinstance(raw.get("allocation"), dict) else {}
    alloc: dict[str, dict[str, Any]] = {}
    for aid in member_ids:
        a = raw_alloc.get(aid)
        if isinstance(a, dict) and (a.get("kind") in _VALID_KINDS):
            if a["kind"] == "patrol_sector":
                a["sector"] = str(a.get("sector", "")).upper()
                if a["sector"] not in SECTORS:
                    a = None
            if a:
                alloc[aid] = a
    # Fill any member the LLM skipped or fumbled with a default sector.
    if len(alloc) < len(member_ids):
        fallback = default_allocation([m for m in member_ids if m not in alloc], bounds)
        alloc.update(fallback)
    return {"reasoning": str(raw.get("reasoning") or "").strip(), "brief": brief, "allocation": alloc}


class GroqStrategist:
    def __init__(self, api_key: str, model: str, temperature: float = 0.4) -> None:
        self.api_key, self.model, self.temperature = api_key, model, temperature

    def plan(self, mission, members, scene, contacts):
        raw = inferenza_json(
            prompt=strategist_user_prompt(mission, members, scene, contacts),
            api_key=self.api_key,
            system_prompt=strategist_system_prompt(),
            model=self.model,
            temperature=self.temperature,
        )
        return _normalise_plan(raw, members, scene.bounds)


class HeuristicStrategist:
    """Deterministic fallback: spread the team across sectors."""

    def plan(self, mission, members, scene, contacts):
        member_ids = [m["id"] for m in members]
        return {
            "reasoning": "Dividing the area into sectors for full coverage.",
            "brief": {"objective": mission.strip(), "constraints": [], "priority": None},
            "allocation": default_allocation(member_ids, scene.bounds),
        }
