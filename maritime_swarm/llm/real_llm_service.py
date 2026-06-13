"""Async adapter around the maritime swarm LLM utilities."""

from __future__ import annotations

import asyncio
from typing import Any

from maritime_swarm.llm.groq_client import inferenza, inferenza_json
from maritime_swarm.llm.system_prompts import SYSTEM_PROMPT_LEAD, SYSTEM_PROMPT_TRACE


class LLMService:
    """Provide non-blocking mission parsing and decision trace generation."""

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    async def parse_mission(self, mission: str) -> dict[str, Any]:
        """Return a structured briefing from natural-language mission text."""
        briefing = await asyncio.to_thread(
            inferenza_json,
            prompt=mission,
            api_key=self.api_key,
            system_prompt=SYSTEM_PROMPT_LEAD,
            model=self.model,
            temperature=0.1,
        )
        parsed = {
            "objective": str(briefing.get("objective", "locate missing buoy")),
            "constraints": list(briefing.get("constraints") or []),
            "priority": briefing.get("priority"),
        }
        parsed["local_intent"] = await self._local_intent(parsed)
        return parsed

    async def decision_trace(self, prompt: str) -> str:
        """Return a concise human-readable trace for an already-made decision."""
        return await asyncio.to_thread(
            inferenza,
            prompt=prompt,
            api_key=self.api_key,
            system_prompt=SYSTEM_PROMPT_TRACE,
            model=self.model,
            temperature=0.2,
        )

    async def _local_intent(self, briefing: dict[str, Any]) -> str:
        prompt = (
            "Convert this mission briefing into one short local_intent sentence "
            "for an autonomous maritime asset. Do not assign tasks.\n\n"
            f"Briefing: {briefing}"
        )
        return await asyncio.to_thread(
            inferenza,
            prompt=prompt,
            api_key=self.api_key,
            system_prompt="Return one concise sentence only.",
            model=self.model,
            temperature=0.1,
        )
