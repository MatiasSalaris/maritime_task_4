"""The per-agent decision/execution loop.

Receives observations from the world model (~10 Hz), asks the planner which
tool to run when idle (or when a new contact appears), and executes the active
tool tick-by-tick by sending actions back. The planner call (a possibly slow
LLM request) runs in a background thread/task so steering stays responsive.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from maritime_swarm.ai_control.observation import Observation
from maritime_swarm.ai_control.planner import Planner
from maritime_swarm.ai_control.scene import Scene
from maritime_swarm.ai_control.tools import (
    Tool,
    ToolContext,
    ToolError,
    ToolRegistry,
    ToolStatus,
)
from maritime_swarm.ai_control.world_client import WorldModelClient

logger = logging.getLogger(__name__)


class AgentBrain:
    """Drives one world-model agent with LLM-selected tools."""

    def __init__(
        self,
        client: WorldModelClient,
        ctx: ToolContext,
        planner: Planner,
        scene: Scene,
        mission: str,
        registry: ToolRegistry,
        min_think_interval: float = 4.0,
    ) -> None:
        self.client = client
        self.ctx = ctx
        self.planner = planner
        self.scene = scene
        self.mission = mission
        self.registry = registry
        self.min_think_interval = min_think_interval

        self.active_tool: Tool | None = None
        self._thinking = False
        self._last_think = 0.0
        self._seen_contacts: set[str] = set()
        self._mission_changed = False

    async def run(self) -> None:
        await self.client.connect()
        await self.client.send_cot(f"{self.ctx.agent_name} online — awaiting first decision.\n")
        try:
            while True:
                msg = await self.client.recv()
                if msg.get("type") != "observation":
                    continue
                obs = Observation.from_payload(msg["payload"])
                await self._on_observation(obs)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # connection dropped, etc.
            logger.warning("[%s] loop ended: %s", self.ctx.agent_id, exc)
        finally:
            await self.client.close()

    async def _on_observation(self, obs: Observation) -> None:
        # Live mission updates: the operator can set, change, or clear the
        # mission in the frontend at any time.
        incoming = (obs.mission or "").strip()
        if incoming != (self.mission or ""):
            self.active_tool = None  # abandon the current plan
            if incoming:
                # New / changed mission → force an immediate replan.
                self.mission = incoming
                self._mission_changed = True
                logger.info("[%s] new mission: %s", self.ctx.agent_id, incoming)
                asyncio.create_task(self.client.send_cot(f"New mission — re-planning: {incoming}\n"))
            else:
                # Mission cleared (operator pressed Reset) → stop and idle.
                self.mission = None
                self._mission_changed = False
                logger.info("[%s] mission cleared — holding station.", self.ctx.agent_id)
                asyncio.create_task(self.client.send_cot("Mission cleared — holding station.\n"))
                asyncio.create_task(
                    self.client.send_action({"speed_kn": 0.0, "planned_path": [], "current_task": "Idle — awaiting orders"})
                )

        # Track newly-appeared contacts; a fresh suspicious contact justifies
        # interrupting the current plan to reconsider.
        new_ids = {c.id for c in obs.contacts} - self._seen_contacts
        self._seen_contacts |= {c.id for c in obs.contacts}
        new_suspicious = any(c.id in new_ids and c.is_suspicious for c in obs.contacts)
        already_investigating = (
            self.active_tool is not None and self.active_tool.name == "investigate_contact"
        )
        # A mission change forces a replan immediately, bypassing the rate limit.
        force = self._mission_changed
        interrupt = force or (new_suspicious and not already_investigating)

        # Decide whether to (re)plan.
        idle = self.active_tool is None
        now = time.monotonic()
        rate_ok = force or (now - self._last_think) >= self.min_think_interval
        # Only plan while there is an active mission; with none, the agent idles.
        if self.mission and (idle or interrupt) and not self._thinking and rate_ok:
            self._mission_changed = False
            self._thinking = True
            asyncio.create_task(self._think(obs))

        # Execute the active tool.
        if self.active_tool is not None:
            inv = self.active_tool.step(obs, self.ctx)
            if inv.action is not None:
                await self.client.send_action(inv.action)
            if inv.finished:
                logger.info(
                    "[%s] %s -> %s (%s)",
                    self.ctx.agent_id,
                    self.active_tool.describe(),
                    inv.status.value,
                    inv.note,
                )
                self.active_tool = None

    async def _think(self, obs: Observation) -> None:
        try:
            decision = await asyncio.to_thread(
                self.planner.decide, obs, self.ctx, self.scene, self.mission, self.registry
            )
            tool = self.registry.build(decision.get("tool"), decision.get("args"), self.ctx)
            reasoning = decision.get("reasoning") or ""
            self.active_tool = tool
            logger.info("[%s] decision: %s | %s", self.ctx.agent_id, tool.describe(), reasoning)
            thought = reasoning.strip() or f"Executing {tool.describe()}."
            await self.client.send_cot(thought + "\n")
        except ToolError as exc:
            logger.warning("[%s] invalid tool call: %s", self.ctx.agent_id, exc)
            self._fallback()
            await self.client.send_cot(f"Invalid tool call ({exc}); falling back to patrol.\n")
        except Exception as exc:  # LLM/network error
            logger.warning("[%s] planner error: %s", self.ctx.agent_id, exc)
            self._fallback()
        finally:
            self._last_think = time.monotonic()
            self._thinking = False

    def _fallback(self) -> None:
        """When planning fails, head to the area centre so the asset keeps moving."""
        clat, clon = self.scene.bounds.center()
        try:
            self.active_tool = self.registry.build("go_to", {"lat": clat, "lon": clon}, self.ctx)
        except ToolError:
            self.active_tool = None
