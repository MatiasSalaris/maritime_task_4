"""Event builders for the swarm protocol."""

from __future__ import annotations


def mission_intent(mission_id: str, mission: str, parsed: dict, entry_node: str) -> dict:
    """Build a peer broadcast carrying parsed operator intent."""
    return {
        "type": "MISSION_INTENT",
        "mission_id": mission_id,
        "nlp_mission": mission,
        "parsed_intent": parsed,
        "entry_node": entry_node,
        "sender": entry_node,
    }


def task_bid(task_id: str, utility: float, sender: str, components: dict) -> dict:
    """Build a deterministic utility bid message."""
    return {
        "type": "TASK_BID",
        "task_id": task_id,
        "utility": utility,
        "sender": sender,
        "components": components,
    }


def handoff_request(task_id: str, obstacle_id: str, requester: str) -> dict:
    """Build a handoff request for a blocked north-sector task."""
    return {
        "type": "HANDOFF_REQUEST",
        "task_id": task_id,
        "contact_id": obstacle_id,
        "target_pos": (58.0, 72.0),
        "requester": requester,
        "blocked_direction": "north",
        "reason": f"{requester} cannot safely continue north around {obstacle_id}",
        "sender": requester,
    }
