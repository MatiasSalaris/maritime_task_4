"""Small OpenAI-compatible client for real LLM calls."""

from __future__ import annotations

import json
from typing import Any

import requests


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
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=30,
    )
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
