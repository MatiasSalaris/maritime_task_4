"""Handoff protocol helpers for blocked-sector recovery."""

from __future__ import annotations

from maritime_swarm.communication.event_messages import task_bid


async def on_handoff_request(agent, event: dict) -> None:
    """Bid on a handoff request unless this agent requested it."""
    task_id = str(event["task_id"])
    requester = str(event["requester"])
    target_pos = tuple(event["target_pos"])
    task = agent.ensure_task(task_id, str(event.get("contact_id", "handoff")), target_pos)
    task.update({
        "status": "collecting_bids",
        "requester": requester,
        "handoff_reason": str(event["reason"]),
        "blocked_direction": event.get("blocked_direction"),
    })
    agent.logger.log(agent.id, f"DISTRIBUTED handoff request {task_id} from {requester}: reason={task['handoff_reason']!r}")

    if agent.id == requester:
        agent.logger.log(agent.id, f"HANDOFF_REQUEST acknowledged locally; I will not bid on blocked sector {task_id}")
    else:
        utility, components = agent.utility_for(target_pos)
        task["bids"][agent.id] = {"utility": utility, "components": components}
        agent.log_utility("HANDOFF_BID", task_id, utility, components)
        await agent.bus.publish(task_bid(task_id, utility, agent.id, components))
    agent.schedule_assignment(task_id)
