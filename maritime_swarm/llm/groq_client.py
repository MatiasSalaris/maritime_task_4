"""Small OpenAI-compatible client for real LLM calls.

Defaults to the Groq endpoint, but the base URL is configurable via
``LLM_BASE_URL`` (or ``GROQ_BASE_URL``) so the swarm can run the exact
open-weight models the challenge suggests (Llama 3.2 3B, Qwen 2.5 7B, Mistral
7B, Gemma 2) served locally via Ollama / LM Studio, e.g.
``LLM_BASE_URL=http://localhost:11434/v1``.
"""

from __future__ import annotations

import json
import os
from typing import Any

import requests

_DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"

# Last observed server token budget (updated on every call, success or 429), so a
# shared client-side limiter can pace accurately and never drive the bucket negative.
_last_remaining_tokens: float | None = None


def _base_url() -> str:
    return (os.getenv("LLM_BASE_URL") or os.getenv("GROQ_BASE_URL") or _DEFAULT_BASE_URL).rstrip("/")


def last_remaining_tokens() -> float | None:
    return _last_remaining_tokens


def _record_budget(headers) -> None:
    global _last_remaining_tokens
    try:
        rem = headers.get("x-ratelimit-remaining-tokens")
        if rem is not None:
            _last_remaining_tokens = float(rem)
    except Exception:
        pass


def inferenza(
    prompt: str,
    api_key: str,
    system_prompt: str | None = None,
    model: str = "llama-3.1-8b-instant",
    json_mode: bool = False,
    temperature: float = 0.2,
) -> str:
    """Return one chat completion string from the Groq OpenAI-compatible API."""
    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    response = requests.post(
        f"{_base_url()}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "User-Agent": "maritime-swarm/1.0"},
        json=payload,
        timeout=45,
    )
    _record_budget(response.headers)   # capture remaining tokens (success or 429)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def inferenza_json(prompt: str, api_key: str, system_prompt: str, **kwargs: Any) -> dict:
    """Return one parsed JSON response from the configured LLM."""
    raw = inferenza(
        prompt=prompt,
        api_key=api_key,
        system_prompt=system_prompt,
        json_mode=True,
        **kwargs,
    )
    return json.loads(raw)
