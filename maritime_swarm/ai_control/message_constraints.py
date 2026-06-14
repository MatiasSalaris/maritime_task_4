"""Protocol constraints for visible peer-to-peer coordination messages."""

from __future__ import annotations

P2P_TEXT_MAX_CHARS = 120
P2P_MAX_MESSAGES_PER_DECISION = 3


def telegraphic_text(value: object, max_chars: int = P2P_TEXT_MAX_CHARS) -> str:
    """Return one-line P2P text constrained to the protocol size."""
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)].rstrip() + "..."
