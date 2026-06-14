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
from typing import Any, Callable

import requests

_DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"


def _base_url() -> str:
    return (os.getenv("LLM_BASE_URL") or os.getenv("GROQ_BASE_URL") or _DEFAULT_BASE_URL).rstrip("/")


def inferenza(
    prompt: str,
    api_key: str,
    system_prompt: str | None = None,
    model: str = "llama-3.1-8b-instant",
    json_mode: bool = False,
    temperature: float = 0.2,
    base_url: str | None = None,
) -> str:
    """Return one chat completion string from an OpenAI-compatible API."""
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
        f"{(base_url or _base_url()).rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "User-Agent": "maritime-swarm/1.0"},
        json=payload,
        timeout=45,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def inferenza_stream(
    prompt: str,
    api_key: str,
    system_prompt: str | None = None,
    model: str = "llama-3.1-8b-instant",
    temperature: float = 0.2,
    on_token: Callable[[str], None] | None = None,
    base_url: str | None = None,
) -> str:
    """Stream one chat completion, invoking ``on_token`` per delta; return the full text.

    Uses Server-Sent Events (``stream: true``) so the agent's reasoning can be
    surfaced live (token-by-token) as it is generated, instead of appearing in
    one lump after the call returns. Raises on a non-2xx status (e.g. 429) the
    same way :func:`inferenza` does, so the caller's rate-limit handling works.
    """
    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }

    parts: list[str] = []
    with requests.post(
        f"{(base_url or _base_url()).rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "User-Agent": "maritime-swarm/1.0"},
        json=payload,
        timeout=45,
        stream=True,
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                break
            try:
                delta = json.loads(data)["choices"][0]["delta"].get("content")
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
            if delta:
                parts.append(delta)
                if on_token is not None:
                    on_token(delta)
    return "".join(parts)


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
