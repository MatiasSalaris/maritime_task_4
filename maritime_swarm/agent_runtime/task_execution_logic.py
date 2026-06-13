"""Deterministic task execution, assignment, and obstacle handling logic."""

from __future__ import annotations

import asyncio

from maritime_swarm.agent_runtime.swarm_event_handlers import finalize_assignment
from maritime_swarm.communication.event_messages import handoff_request
from maritime_swarm.demo.demo_logger import Colors
from maritime_swarm.domain.agent_state import AgentMode
from maritime_swarm.domain.navigation_planning import avoidance_waypoint
from maritime_swarm.domain.utility_scoring import calculate_utility, format_bids
from maritime_swarm.llm.decision_trace_prompts import assignment_prompt, handoff_prompt


class AgentTaskLogic:
    """Mixin containing deterministic task and local execution decisions."""

    def ensure_task(self, task_id: str, contact_id: str, target_pos: tuple[float, float]) -> dict:
        """Return an existing task registry entry or create one."""
        return self.state.distributed_state["global_tasks"].setdefault(
            task_id,
            {"contact_id": contact_id, "target_pos": target_pos, "status": "pending", "bids": {}, "winner": None},
        )

    def utility_for(self, target_pos: tuple[float, float]) -> tuple[float, dict[str, float]]:
        """Compute this agent's deterministic utility for a target position."""
        physical = self.state.physical_state
        return calculate_utility(physical["pos"], physical["battery"], physical["sensor_quality"], target_pos)

    def schedule_assignment(self, task_id: str) -> None:
        """Schedule bid-window finalization for a task."""
        task = asyncio.create_task(finalize_assignment(self, task_id), name=f"{self.id}:{task_id}:finalize")
        self._tasks.append(task)

    def log_utility(self, prefix: str, task_id: str, utility: float, components: dict[str, float]) -> None:
        """Log the utility formula and component values for a bid."""
        self.logger.log(
            self.id,
            f"{prefix} {task_id}; utility = 0.5*{components['normalized_distance_score']:.3f} "
            f"+ 0.3*{components['normalized_battery']:.3f} + 0.2*{components['sensor_quality']:.3f} = {utility:.3f}",
        )

    def apply_assignment(self, task_id: str, task: dict, winner: str, bid: dict) -> None:
        """Apply deterministic argmax result and request an LLM trace."""
        task.update({"winner": winner, "status": "assigned", "winning_utility": bid["utility"]})
        assignment = self._assignment_state(task_id, task, winner)
        self.logger.log(self.id, f"{Colors.BOLD}ARGMAX bids for {task_id}: {format_bids(task['bids'])} -> winner={winner} ({bid['utility']:.3f}){Colors.RESET}")
        self._tasks.append(asyncio.create_task(self._record_trace(task_id, task, winner, bid["utility"], assignment)))

    def _assignment_state(self, task_id: str, task: dict, winner: str) -> str:
        if winner == self.id:
            self.state.state = AgentMode.EXECUTING
            self.state.active_task = task_id
            return f"I won and am executing {task_id}."
        if task.get("requester") == self.id:
            self.state.state = AgentMode.EXECUTING
            self.state.active_task = "alternate_patrol_after_handoff"
            return f"I handed off {task_id} to {winner}; I am continuing in an alternate safe direction."
        self.state.state = AgentMode.IDLE
        self.state.active_task = None
        return f"I am yielding; {winner} owns {task_id}."

    async def _record_trace(self, task_id: str, task: dict, winner: str, utility: float, assignment: str) -> None:
        prompt = handoff_prompt(self.id, task_id, task, winner, utility, assignment) if task_id.startswith("handoff_") else assignment_prompt(self.id, task_id, winner, utility, assignment)
        self.logger.log(self.id, f"LLM_CALL decision trace using {self.llm.model}")
        trace = await self.llm.decision_trace(prompt)
        self.state.cognitive_state["decision_traces"].append(trace)
        self.logger.log(self.id, f"DECISION_TRACE {trace}")

    async def handle_local_obstacle(self, obstacle_id: str, obstacle_pos: tuple[float, float], blocks_direction: str | None) -> None:
        """Evaluate and handle a local obstacle while executing."""
        if self.state.state != AgentMode.EXECUTING or self.state.active_task is None:
            self.logger.log(self.id, f"OBSTACLE {obstacle_id} stored locally; I am not executing, so no reroute needed")
            return
        task = self.state.distributed_state["global_tasks"].get(self.state.active_task, {})
        if task.get("target_pos") is None:
            self.logger.log(self.id, f"OBSTACLE {obstacle_id} detected; no target route stored, continuing cautious execution")
            return
        self.state.state = AgentMode.EVALUATING
        self.logger.log(self.id, f"{Colors.RED}OBSTACLE {obstacle_id} on route while executing {self.state.active_task}; state -> EVALUATING{Colors.RESET}")
        await asyncio.sleep(0.2)
        await self._reroute_or_handoff(obstacle_id, obstacle_pos, blocks_direction, task)

    async def _reroute_or_handoff(self, obstacle_id: str, obstacle_pos: tuple[float, float], blocks_direction: str | None, task: dict) -> None:
        if blocks_direction == "north":
            self.state.active_task = "alternate_east_sweep"
            self.state.state = AgentMode.EXECUTING
            task["avoidance"] = {"obstacle_id": obstacle_id, "obstacle_pos": obstacle_pos, "policy": "north blocked; hand off blocked sector and continue alternate direction"}
            handoff_id = f"handoff_north_sector_from_{self.id}"
            self.logger.log(self.id, f"{Colors.BOLD}NORTH_BLOCKED by {obstacle_id}; broadcasting HANDOFF_REQUEST for {handoff_id}; continuing alternate_east_sweep{Colors.RESET}")
            await self.bus.publish(handoff_request(handoff_id, obstacle_id, self.id))
            return
        waypoint = avoidance_waypoint(self.state.physical_state["pos"], obstacle_pos, tuple(task["target_pos"]))
        task["avoidance"] = {"obstacle_id": obstacle_id, "obstacle_pos": obstacle_pos, "waypoint": waypoint, "policy": "deterministic lateral offset"}
        self.state.state = AgentMode.EXECUTING
        self.logger.log(self.id, f"{Colors.BOLD}AVOIDANCE_PLAN waypoint={waypoint}; state -> EXECUTING; continuing {self.state.active_task}{Colors.RESET}")
