"""The open-ended agent decider.

One call returns the agent's reasoning, any coordination messages, and a single
action (tool call). The real planner (GroqDecider) is a pure LLM — no keyword
rules. A small HeuristicDecider keeps the loop alive offline / in tests.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from maritime_swarm.ai_control.geo import haversine_km
from maritime_swarm.ai_control.message_constraints import P2P_MAX_MESSAGES_PER_DECISION, telegraphic_text
from maritime_swarm.ai_control.observation import Observation
from maritime_swarm.ai_control.prompts import build_decision_system_prompt, build_decision_user_prompt
from maritime_swarm.ai_control.scene import Scene
from maritime_swarm.ai_control.tools import ToolContext, ToolRegistry
from maritime_swarm.llm.groq_client import inferenza_json

logger = logging.getLogger(__name__)

_MSG_TYPES = {"proposal", "ack", "objection", "handoff", "report", "status"}


def _search_priority(mission: str | None) -> str:
    text = (mission or "").lower()
    if any(word in text for word in ("veloc", "speed", "rapido", "quick", "fast")):
        return "speed"
    if any(word in text for word in ("copertura", "coverage", "accurata", "dense", "completa")):
        return "coverage"
    return "balanced"


def normalise_decision(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce an LLM response into {reasoning, messages, action}."""
    action = raw.get("action") or {}
    if not isinstance(action, dict):
        action = {}
    tool = action.get("tool") or action.get("name")
    args = action.get("args") or action.get("arguments") or {}
    if not isinstance(args, dict):
        args = {}

    msgs_raw = raw.get("messages") or []
    if isinstance(msgs_raw, dict):
        msgs_raw = [msgs_raw]
    messages = []
    for m in msgs_raw if isinstance(msgs_raw, list) else []:
        if not isinstance(m, dict):
            continue
        text = telegraphic_text(m.get("content") or m.get("text") or "")
        if not text:
            continue
        mtype = str(m.get("type") or "status").lower().strip()
        if mtype not in _MSG_TYPES:
            mtype = "status"
        messages.append({"to": str(m.get("to") or "all"), "type": mtype, "content": text})

    return {
        "reasoning": str(raw.get("reasoning") or "").strip(),
        "messages": messages[:P2P_MAX_MESSAGES_PER_DECISION],
        "tool": tool,
        "args": args,
    }


class AgentDecider(Protocol):
    def decide(
        self, obs: Observation, ctx: ToolContext, scene: Scene, mission: str,
        peers: list[dict[str, Any]], shared_contacts: list[dict[str, Any]],
        messages: list[dict[str, Any]], current_task: str | None, registry: ToolRegistry,
        task_status: str = "idle", silent_peers: list[str] | None = None,
        outbox: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        ...


class GroqDecider:
    def __init__(self, api_key: str, model: str, temperature: float = 0.3) -> None:
        self.api_key, self.model, self.temperature = api_key, model, temperature

    def decide(self, obs, ctx, scene, mission, peers, shared_contacts, messages, current_task, registry,
               task_status="idle", silent_peers=None, outbox=None):
        raw = inferenza_json(
            prompt=build_decision_user_prompt(
                obs, ctx, scene, mission, peers, shared_contacts, messages, current_task,
                task_status, silent_peers, outbox),
            api_key=self.api_key,
            system_prompt=build_decision_system_prompt(registry),
            model=self.model,
            temperature=self.temperature,
        )
        return normalise_decision(raw)


class HeuristicDecider:
    """Offline fallback: spread by id, investigate suspicious, hold otherwise.

    Not clever — only so the loop runs without an API key. Real behaviour comes
    from the LLM.
    """

    _SECTORS = ["NW", "NE", "SW", "SE"]

    def _sector_from_position(self, obs, scene) -> str:
        b = scene.bounds
        lat_mid = (b.lat_min + b.lat_max) / 2
        lon_mid = (b.lon_min + b.lon_max) / 2
        if obs.lat >= lat_mid and obs.lon <= lon_mid:
            return "NW"
        if obs.lat >= lat_mid and obs.lon > lon_mid:
            return "NE"
        if obs.lat < lat_mid and obs.lon <= lon_mid:
            return "SW"
        return "SE"

    def decide(self, obs, ctx, scene, mission, peers, shared_contacts, messages, current_task, registry,
               task_status="idle", silent_peers=None, outbox=None):
        buoys = [c for c in obs.contacts if c.is_buoy]
        if buoys:
            nearest = min(buoys, key=lambda c: haversine_km(obs.lat, obs.lon, c.lat, c.lon))
            return normalise_decision({
                "reasoning": f"Boa dispersa {nearest.id} rilevata nel raggio sensore; mi avvicino per confermare la posizione.",
                "messages": [{"to": "all", "type": "report", "content": f"Rilevata boa dispersa {nearest.id}."}],
                "action": {"tool": "investigate_contact", "args": {"contact_id": nearest.id}},
            })
        susp = [c for c in obs.contacts if c.is_suspicious]
        if susp:
            nearest = min(susp, key=lambda c: haversine_km(obs.lat, obs.lon, c.lat, c.lon))
            return normalise_decision({
                "reasoning": f"Contatto sospetto {nearest.id} nel raggio sensore; mi avvicino per identificarlo.",
                "messages": [{"to": "all", "type": "status", "content": f"Ispeziono {nearest.id}."}],
                "action": {"tool": "investigate_contact", "args": {"contact_id": nearest.id}},
            })
        mission_l = (mission or "").lower()
        if any(word in mission_l for word in ("patrol", "pattuglia", "anomaly", "anomalia", "ais")):
            sector = self._sector_from_position(obs, scene)
            return normalise_decision({
                "reasoning": f"Nessun contatto rilevato; dalla mia posizione il settore {sector} e' la copertura piu vicina.",
                "messages": [],
                "action": {"tool": "patrol_sector", "args": {"sector": sector}},
            })
        sector = self._sector_from_position(obs, scene)
        return normalise_decision({
            "reasoning": f"Nessun contatto rilevato; dalla mia posizione propongo ricerca nel settore {sector} con priorità {_search_priority(mission)}.",
            "messages": [],
            "action": {"tool": "search_area", "args": {"sector": sector, "priority": _search_priority(mission)}},
        })
