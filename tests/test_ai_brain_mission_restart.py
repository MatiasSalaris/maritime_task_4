"""Regression tests for mission restart after successful completion."""

from __future__ import annotations

import asyncio
import time

import pytest

from maritime_swarm.ai_control.blackboard import SharedContact
from maritime_swarm.ai_control.brain import AgentBrain
from maritime_swarm.ai_control.observation import Observation
from maritime_swarm.ai_control.scene import Scene
from maritime_swarm.ai_control.tools import Bounds, ToolContext, ToolRegistry


class FakeClient:
    """Collect outbound messages without opening a WebSocket."""

    def __init__(self) -> None:
        self.actions: list[dict] = []
        self.cot: list[str] = []
        self.p2p: list[dict] = []
        self.mission_completions: list[dict] = []

    async def send_action(self, payload: dict) -> None:
        self.actions.append(payload)

    async def send_cot(self, chunk: str) -> None:
        self.cot.append(chunk)

    async def send_p2p(self, to: str, msg_type: str, content: dict, reasoning: str | None = None) -> None:
        self.p2p.append({"to": to, "msg_type": msg_type, "content": content, "reasoning": reasoning})

    async def send_mission_complete(self, result: dict) -> None:
        self.mission_completions.append(result)


class FakeDecider:
    """No-op decider; this test exercises pre-decision mission handling."""

    def decide(self, *args, **kwargs) -> dict:
        return {"reasoning": "", "messages": [], "tool": "none", "args": {}}


def make_brain(client: FakeClient) -> AgentBrain:
    bounds = Bounds(lat_min=37.42, lat_max=37.60, lon_min=15.00, lon_max=15.28)
    scene = Scene(bounds=bounds)
    ctx = ToolContext(
        agent_id="agent_0",
        agent_name="Alpha",
        agent_type="USV",
        cruise_speed_kn=28.0,
        bounds=bounds,
        scene=scene,
    )
    brain = AgentBrain(client, ctx, FakeDecider(), scene, "Find the missing buoy", ToolRegistry())
    brain._cooldown_until = time.monotonic() + 999.0
    return brain


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_new_mission_after_buoy_completion_does_not_reuse_stale_buoy() -> None:
    client = FakeClient()
    brain = make_brain(client)
    brain.view.contacts["buoy_1"] = SharedContact(
        id="buoy_1",
        lat=37.50,
        lon=15.10,
        label="BUOY",
        reported=True,
        updated_t=20.0,
    )

    await brain._on_observation(Observation(
        agent_id="agent_0",
        lat=37.50,
        lon=15.10,
        heading=0.0,
        speed_kn=0.0,
        world_time=21.0,
        mission="Find the missing buoy",
        mission_status="completed",
        mission_result={"contact_id": "buoy_1"},
    ))

    assert brain._current_task == "Missione completata: boa buoy_1 trovata"

    await brain._on_observation(Observation(
        agent_id="agent_0",
        lat=37.50,
        lon=15.10,
        heading=0.0,
        speed_kn=0.0,
        world_time=30.0,
        mission="Patrol the south sector",
        mission_status="active",
    ))
    await asyncio.sleep(0)

    assert brain.mission == "Patrol the south sector"
    assert brain._current_task == "Ricalcolo missione"
    assert brain.view.contacts == {}
    assert client.mission_completions == []


@pytest.mark.anyio
async def test_same_mission_text_can_be_reactivated_after_completion() -> None:
    client = FakeClient()
    brain = make_brain(client)
    brain.view.contacts["buoy_1"] = SharedContact(
        id="buoy_1",
        lat=37.50,
        lon=15.10,
        label="BUOY",
        reported=True,
        updated_t=20.0,
    )

    await brain._on_observation(Observation(
        agent_id="agent_0",
        lat=37.50,
        lon=15.10,
        heading=0.0,
        speed_kn=0.0,
        world_time=21.0,
        mission="Find the missing buoy",
        mission_status="completed",
        mission_result={"contact_id": "buoy_1"},
    ))

    await brain._on_observation(Observation(
        agent_id="agent_0",
        lat=37.50,
        lon=15.10,
        heading=0.0,
        speed_kn=0.0,
        world_time=30.0,
        mission="Find the missing buoy",
        mission_status="active",
    ))
    await asyncio.sleep(0)

    assert brain.mission == "Find the missing buoy"
    assert brain._current_task == "Ricalcolo missione"
    assert brain._mission_complete_contact is None
    assert brain.view.contacts == {}
