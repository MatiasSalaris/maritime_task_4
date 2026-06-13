"""Environment and .env loading helpers."""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from .env without overriding existing env vars."""
    env_path = path or Path.cwd() / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def require_api_key() -> str:
    """Return the configured API key or raise a clear setup error."""
    api_key = os.getenv("API_KEY") or os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "API_KEY/GROQ_API_KEY non impostata. Usa: export GROQ_API_KEY=..."
        )
    return api_key


def configured_model() -> str:
    """Return the selected Groq model name."""
    return os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
