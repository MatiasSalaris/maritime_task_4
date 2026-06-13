"""Prompt builders for real LLM decision traces."""

from __future__ import annotations


def assignment_prompt(agent_id: str, task_id: str, winner: str, utility: float, assignment: str) -> str:
    """Build a trace prompt for deterministic search-task assignment."""
    return (
        f"Agent: {agent_id}\nTask: {task_id}\n"
        "Event: deterministic utility bidding assigned a search sector before mission success.\n"
        f"Winner: {winner}\nWinning utility: {utility:.3f}\n"
        f"My assignment outcome: {assignment}"
    )


def handoff_prompt(agent_id: str, task_id: str, task: dict, winner: str, utility: float, assignment: str) -> str:
    """Build a trace prompt for deterministic handoff assignment."""
    return (
        f"Agent: {agent_id}\nTask: {task_id}\n"
        "Event: deterministic handoff bidding completed.\n"
        f"Reason: {task.get('handoff_reason', 'not specified')}\n"
        f"Winner: {winner}\nWinning utility: {utility:.3f}\n"
        f"My assignment outcome: {assignment}"
    )
