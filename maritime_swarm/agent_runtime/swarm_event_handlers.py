"""Handlers for peer-to-peer swarm events received from the event bus."""

from __future__ import annotations

import asyncio

from maritime_swarm.communication.event_messages import task_bid
from maritime_swarm.domain.agent_state import AgentMode
from maritime_swarm.domain.utility_scoring import select_winner


def on_mission_intent(agent, event: dict) -> None:
    """Accept a mission briefing into distributed and cognitive state."""
    mission = {
        "mission_id": str(event["mission_id"]),
        "nlp_mission": str(event["nlp_mission"]),
        "parsed_intent": dict(event["parsed_intent"]),
        "entry_node": str(event["entry_node"]),
        "status": "accepted",
    }
    agent.state.distributed_state["mission_intent"] = mission
    agent.state.cognitive_state["local_intent"] = mission["parsed_intent"]["local_intent"]
    agent.logger.log(agent.id, f"DISTRIBUTED mission_intent accepted from {mission['entry_node']}: id={mission['mission_id']}, objective={mission['parsed_intent']['objective']}, priority={mission['parsed_intent']['priority']}")
    agent.logger.log(agent.id, f"COGNITIVE local_intent -> {agent.state.cognitive_state['local_intent']!r}")


def on_buoy_detected(agent, event: dict) -> None:
    """Accept one direct buoy detection as mission success."""
    contact_id = str(event["contact_id"])
    detected_by = str(event["detected_by"])
    contact_pos = tuple(event["contact_pos"])
    agent.state.distributed_state["shared_contacts"][contact_id] = {
        "type": "buoy",
        "status": "detected",
        "detected_by": detected_by,
        "pos": contact_pos,
        "validation_policy": "single asset detection is sufficient",
    }
    mission = agent.state.distributed_state.get("mission_intent")
    if mission:
        mission.update({"status": "complete", "success_contact": contact_id, "completed_by": detected_by})
    for task in agent.state.distributed_state["global_tasks"].values():
        if task.get("status") not in {"complete", "closed_by_success"}:
            task["status"] = "closed_by_success"
    agent.state.state = AgentMode.IDLE
    agent.state.active_task = None
    agent.state.cognitive_state["local_intent"] = f"mission complete: buoy {contact_id} detected by {detected_by}"
    agent.logger.log(agent.id, f"DISTRIBUTED shared_contacts[{contact_id}] <- buoy detected_by={detected_by} pos={contact_pos}; accepted without peer comparison")
    agent.logger.log(agent.id, f"MISSION_COMPLETE buoy={contact_id} detected_by={detected_by}; stopping active tasking")


async def on_task_trigger(agent, event: dict) -> None:
    """Bid on a task and schedule deterministic assignment."""
    task_id = str(event["task_id"])
    target_pos = tuple(event["target_pos"])
    task = agent.ensure_task(task_id, str(event["contact_id"]), target_pos)
    agent.state.state = AgentMode.EVALUATING
    task["status"] = "collecting_bids"
    utility, components = agent.utility_for(target_pos)
    task["bids"][agent.id] = {"utility": utility, "components": components}
    agent.log_utility("TASK_TRIGGER", task_id, utility, components)
    await agent.bus.publish(task_bid(task_id, utility, agent.id, components))
    agent.schedule_assignment(task_id)


def on_task_bid(agent, event: dict) -> None:
    """Store one bid in the distributed task registry."""
    task = agent.state.distributed_state["global_tasks"].setdefault(
        str(event["task_id"]), {"contact_id": None, "target_pos": None, "status": "collecting_bids", "bids": {}, "winner": None}
    )
    task["bids"][str(event["sender"])] = {"utility": float(event["utility"]), "components": dict(event.get("components", {}))}
    agent.logger.log(agent.id, f"DISTRIBUTED global_tasks[{event['task_id']}].bids[{event['sender']}]={event['utility']:.3f}")


async def finalize_assignment(agent, task_id: str) -> None:
    """Close a bid window and apply the same argmax result on every agent."""
    await asyncio.sleep(agent.BID_COLLECTION_SECONDS)
    task = agent.state.distributed_state["global_tasks"][task_id]
    if task["winner"] is not None:
        return
    winner, bid = select_winner(task["bids"])
    agent.apply_assignment(task_id, task, winner, bid)
