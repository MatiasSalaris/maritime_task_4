"""Compatibility facade for LLM client functions and prompt templates."""

from swarm.llm_client import inferenza, inferenza_json
from swarm.prompts import SYSTEM_PROMPT_LEAD, SYSTEM_PROMPT_TRACE

__all__ = [
    "SYSTEM_PROMPT_LEAD",
    "SYSTEM_PROMPT_TRACE",
    "inferenza",
    "inferenza_json",
]
