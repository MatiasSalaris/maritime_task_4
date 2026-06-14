"""Message schema checks for the swarm event protocol."""

from __future__ import annotations

from typing import Any

REQUIRED_FIELDS = {
    "MISSION_INTENT": {"mission_id", "parsed_intent", "briefing", "entry_node", "sender"},
    "BUOY_DETECTED": {"contact_id", "contact_pos", "detected_by", "sender"},
    "TASK_TRIGGER": {"task_id", "contact_id", "target_pos", "sender"},
    "TASK_BID": {"task_id", "utility", "sender"},
    "HANDOFF_REQUEST": {"task_id", "target_pos", "requester", "reason", "sender"},
}


def validate_message(event: dict[str, Any]) -> None:
    """Raise ValueError if an event is missing required protocol fields."""
    event_type = event.get("type")
    if not isinstance(event_type, str):
        raise ValueError("message requires string field 'type'")
    required = REQUIRED_FIELDS.get(event_type)
    if required is None:
        raise ValueError(f"unknown message type: {event_type}")
    missing = sorted(field for field in required if field not in event)
    if missing:
        raise ValueError(f"{event_type} missing fields: {', '.join(missing)}")
