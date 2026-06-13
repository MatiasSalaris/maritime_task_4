"""Operator ingestion and local sensor actions for a maritime agent."""

from __future__ import annotations

import math

from maritime_swarm.communication.event_messages import mission_intent
from maritime_swarm.demo.demo_logger import Colors


async def receive_operator_mission(agent, mission_id: str, mission: str, operator_pos: tuple[float, float]) -> None:
    """Parse operator NLP, update entry-node role, and broadcast mission intent."""
    distance = math.dist(operator_pos, agent.state.physical_state["pos"])
    agent.logger.log(agent.id, f"LLM_CALL mission reformulation using {agent.llm.model}")
    parsed = await agent.llm.parse_mission(mission)
    agent.logger.log(
        agent.id,
        f"{Colors.BOLD}DIRECT_OPERATOR_NLP received by proximity ({distance:.1f}m). Acting as temporary entry node.{Colors.RESET}",
    )
    agent.logger.log(agent.id, f"OPERATOR_NLP raw={mission!r}")
    agent.logger.log(agent.id, f"ENTRY_NODE parsed mission={parsed}; broadcasting MISSION_INTENT to peers")
    await agent.bus.publish(mission_intent(mission_id, mission, parsed, agent.id))


async def detect_buoy(agent, contact_id: str, contact_pos: tuple[float, float]) -> None:
    """Record a certain buoy detection and broadcast mission success evidence."""
    observation = {"id": contact_id, "hypothesis": "buoy", "observer": agent.id, "pos": contact_pos}
    agent.state.physical_state["raw_contacts"].append(observation)
    agent.state.cognitive_state["local_beliefs"][contact_id] = {
        "hypothesis": "buoy",
        "pos": contact_pos,
        "certainty": "direct_detection",
    }
    agent.logger.log(agent.id, f"{Colors.BOLD}BUOY_DETECTED locally {observation}; treating as certain mission contact{Colors.RESET}")
    await agent.bus.publish({
        "type": "BUOY_DETECTED",
        "contact_id": contact_id,
        "contact_pos": contact_pos,
        "detected_by": agent.id,
        "sender": agent.id,
    })


async def detect_obstacle(agent, obstacle_id: str, obstacle_pos: tuple[float, float], blocks_direction: str | None) -> None:
    """Handle a local obstacle without peer validation; may trigger handoff."""
    observation = {
        "id": obstacle_id,
        "hypothesis": "obstacle",
        "observer": agent.id,
        "pos": obstacle_pos,
        "blocks_direction": blocks_direction,
    }
    agent.state.physical_state["raw_contacts"].append(observation)
    agent.state.cognitive_state["local_beliefs"][obstacle_id] = {
        "hypothesis": "obstacle",
        "pos": obstacle_pos,
        "blocks_direction": blocks_direction,
    }
    agent.logger.log(agent.id, f"{Colors.RED}LOCAL_OBSTACLE_DETECTED {observation}; handling locally without peer validation{Colors.RESET}")
    await agent.handle_local_obstacle(obstacle_id, obstacle_pos, blocks_direction)
