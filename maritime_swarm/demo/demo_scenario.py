"""Deterministic demo scenario that drives the operator-to-swarm storyline."""

from __future__ import annotations

import asyncio
import math

from maritime_swarm.agent_runtime.maritime_agent import MaritimeAgent
from maritime_swarm.communication.async_event_bus import EventBus
from maritime_swarm.demo.demo_logger import DemoLogger
from maritime_swarm.debugging import capture_agent_state
from maritime_swarm.domain.utility_scoring import format_bids

MISSION_TEXT = "Find the missing buoy in this region, prioritise speed, and stop once it is detected."
OPERATOR_POS = (0.0, 0.0)
SEARCH_TARGET = (58.0, 72.0)


async def run_demo(bus: EventBus, agents: dict[str, MaritimeAgent], logger: DemoLogger) -> None:
    """Run the obstacle-before-success scenario and then shut down agents."""
    logger.log("SIM", "starting agent tasks")
    await asyncio.gather(*(agent.start() for agent in agents.values()))
    await _operator_mission(agents, logger)
    await _assign_initial_search(bus, logger)
    await _inject_blocking_obstacle(agents, logger)
    await _complete_after_handoff(agents, logger)
    await _final_snapshot(agents, logger)
    await asyncio.gather(*(agent.shutdown() for agent in agents.values()), return_exceptions=True)
    logger.log("SIM", "simulation complete")


async def _operator_mission(agents: dict[str, MaritimeAgent], logger: DemoLogger) -> None:
    await asyncio.sleep(0.5)
    closest = min(agents.values(), key=lambda agent: math.dist(OPERATOR_POS, agent.state.physical_state["pos"]))
    logger.log("OPERATOR", f"NLP mission assignment: {MISSION_TEXT!r}")
    logger.log("SIM", f"operator_pos={OPERATOR_POS}; closest entry node={closest.id} at pos={closest.state.physical_state['pos']}")
    await closest.receive_operator_mission("M-001", MISSION_TEXT, OPERATOR_POS)


async def _assign_initial_search(bus: EventBus, logger: DemoLogger) -> None:
    await asyncio.sleep(0.5)
    logger.log("SIM", "T=1.0 mission context has been broadcast; assign search_north_sector before buoy is found")
    await bus.publish({
        "type": "TASK_TRIGGER",
        "task_id": "search_north_sector",
        "contact_id": "SEARCH_NORTH",
        "target_pos": SEARCH_TARGET,
        "sender": "SIM",
    })


async def _inject_blocking_obstacle(agents: dict[str, MaritimeAgent], logger: DemoLogger) -> None:
    await asyncio.sleep(1.0)
    logger.log("SIM", "T=2.0 obstacle before mission success: USV-2 cannot continue north")
    await agents["USV-2"].detect_obstacle("O9", obstacle_pos=(54.0, 52.0), blocks_direction="north")


async def _complete_after_handoff(agents: dict[str, MaritimeAgent], logger: DemoLogger) -> None:
    await asyncio.sleep(1.1)
    logger.log("SIM", "T=3.3 handoff winner reaches search area and detects buoy C17")
    await agents["USV-3"].detect_buoy("C17", contact_pos=SEARCH_TARGET)
    await asyncio.sleep(0.8)


async def _final_snapshot(agents: dict[str, MaritimeAgent], logger: DemoLogger) -> None:
    logger.log("SIM", "final distributed snapshots")
    for agent in agents.values():
        mission = agent.state.distributed_state.get("mission_intent") or {}
        contact = agent.state.distributed_state["shared_contacts"].get("C17", {})
        task = agent.state.distributed_state["global_tasks"].get("search_north_sector", {})
        handoff = agent.state.distributed_state["global_tasks"].get("handoff_north_sector_from_USV-2", {})
        local_obstacles = [
            item["id"]
            for item in agent.state.physical_state["raw_contacts"]
            if item.get("hypothesis") == "obstacle"
        ]
        logger.log(
            "SIM",
            f"{agent.id}: mode={agent.state.state.value}, active_task={agent.state.active_task}, "
            f"mission={mission.get('mission_id')} status={mission.get('status')} completed_by={mission.get('completed_by')} "
            f"via={mission.get('entry_node')}, C17={contact.get('type')} detected_by={contact.get('detected_by')} "
            f"policy={contact.get('validation_policy')}, local_obstacles={local_obstacles}, "
            f"search_winner={task.get('winner')} search_status={task.get('status')} avoidance={task.get('avoidance')}, "
            f"handoff_winner={handoff.get('winner')} handoff_bids={format_bids(handoff.get('bids', {}))}",
        )
    if getattr(logger, "debug_enabled", False) and hasattr(logger, "log_debug"):
        payload = {
            agent.id: capture_agent_state(agent, limit_events=50, limit_traces=20)
            for agent in agents.values()
        }
        logger.log_debug("SIM", "final_swarm_snapshot", payload)
