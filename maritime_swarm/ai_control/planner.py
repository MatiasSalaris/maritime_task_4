"""Tactical planner: decide whether to react to a sensed contact.

Each agent's baseline task (patrol sector, escort, visit POIs…) runs
automatically from its assignment. The tactician is consulted only when there is
something to react to, and returns one of:

    {"action": "continue"}                          — stay on the baseline task
    {"action": "investigate", "contact_id": ...}    — break off to identify
    {"action": "report", "contact_id": ..., "classification": ..., "rationale": ...}

This keeps the LLM doing the *judgement* (is this an anomaly? worth reporting?)
while routine movement stays deterministic and grounded.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from maritime_swarm.ai_control.geo import haversine_km
from maritime_swarm.ai_control.observation import Observation
from maritime_swarm.ai_control.prompts import tactical_system_prompt, tactical_user_prompt
from maritime_swarm.ai_control.tools import ToolContext
from maritime_swarm.llm.groq_client import inferenza_json

logger = logging.getLogger(__name__)

_ACTIONS = {"continue", "investigate", "report"}


class TacticalPlanner(Protocol):
    def decide_reactive(
        self, obs: Observation, ctx: ToolContext, mission: str, brief: dict[str, Any] | None,
        assignment_label: str, peers: list[dict[str, Any]], focus: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...


def _normalise_reactive(raw: dict[str, Any]) -> dict[str, Any]:
    action = str(raw.get("action") or raw.get("tool") or "continue").lower().strip()
    if action not in _ACTIONS:
        action = "continue"
    return {
        "action": action,
        "contact_id": (str(raw.get("contact_id")).strip() if raw.get("contact_id") else None),
        "classification": (str(raw.get("classification") or "").upper().strip() or None),
        "rationale": str(raw.get("rationale") or "").strip(),
        "reasoning": str(raw.get("reasoning") or "").strip(),
    }


class GroqTactician:
    def __init__(self, api_key: str, model: str, temperature: float = 0.2) -> None:
        self.api_key, self.model, self.temperature = api_key, model, temperature

    def decide_reactive(self, obs, ctx, mission, brief, assignment_label, peers, focus=None):
        raw = inferenza_json(
            prompt=tactical_user_prompt(obs, ctx, mission, brief, assignment_label, peers, focus),
            api_key=self.api_key,
            system_prompt=tactical_system_prompt(),
            model=self.model,
            temperature=self.temperature,
        )
        return _normalise_reactive(raw)


class HeuristicTactician:
    """No-LLM reactions: investigate a suspicious contact, report once close."""

    def decide_reactive(self, obs, ctx, mission, brief, assignment_label, peers, focus=None):
        if focus and focus.get("id"):
            # A contact we just identified — report it if it looked suspicious.
            if focus.get("flagged") or str(focus.get("label", "")).upper() == "UNKNOWN":
                return _normalise_reactive({
                    "action": "report", "contact_id": focus["id"], "classification": "ANOMALY",
                    "rationale": "Identified contact does not match a commercial AIS pattern.",
                    "reasoning": f"Identified {focus['id']}; reporting as anomaly.",
                })
            return _normalise_reactive({"action": "continue"})
        suspicious = [c for c in obs.contacts if c.is_suspicious]
        if not suspicious:
            return _normalise_reactive({"action": "continue"})
        nearest = min(suspicious, key=lambda c: haversine_km(obs.lat, obs.lon, c.lat, c.lon))
        dist = haversine_km(obs.lat, obs.lon, nearest.lat, nearest.lon)
        if dist <= max(0.6, ctx.arrival_km * 2):
            return _normalise_reactive({
                "action": "report", "contact_id": nearest.id, "classification": "ANOMALY",
                "rationale": f"{nearest.label} contact with no commercial AIS match at close range.",
                "reasoning": f"Closed on {nearest.id}; assessing as anomaly and reporting.",
            })
        return _normalise_reactive({
            "action": "investigate", "contact_id": nearest.id,
            "reasoning": f"Suspicious {nearest.label} contact {nearest.id} in range; closing to identify.",
        })
