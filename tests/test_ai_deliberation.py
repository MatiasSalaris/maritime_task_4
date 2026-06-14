"""Tests for the bounded multi-agent deliberation protocol."""

from __future__ import annotations

import pytest

from maritime_swarm.ai_control.blackboard import PeerInfo
from maritime_swarm.ai_control.brain import AgentBrain
from maritime_swarm.ai_control.deliberation import DeliberationSession, Proposal
from maritime_swarm.ai_control.navigation_tools import default_registry
from maritime_swarm.ai_control.observation import Observation
from maritime_swarm.ai_control.scene import Scene
from maritime_swarm.ai_control.tools import Bounds, ToolContext


class FakeClient:
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


class FixedDecider:
    def decide(self, *args, **kwargs) -> dict:
        return {
            "reasoning": "Propongo una copertura compatibile con la missione.",
            "messages": [],
            "tool": "search_area",
            "args": {"sector": "NW", "priority": "speed"},
        }


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


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
    return AgentBrain(client, ctx, FixedDecider(), scene, "Find the missing buoy", default_registry())


def make_obs() -> Observation:
    return Observation(
        agent_id="agent_0",
        lat=37.50,
        lon=15.10,
        heading=0.0,
        speed_kn=0.0,
        world_time=100.0,
        mission="Find the missing buoy",
        mission_status="active",
    )


def later_obs(seconds: float) -> Observation:
    obs = make_obs()
    obs.world_time += seconds
    return obs


@pytest.mark.anyio
async def test_deliberation_sends_proposal_before_executing_tool() -> None:
    client = FakeClient()
    brain = make_brain(client)
    obs = make_obs()

    brain._start_deliberation("mission", obs)
    assert brain._deliberation is not None
    await brain._advance_deliberation(obs, FixedDecider().decide(), "Scelgo la corsia nord-ovest.")

    assert brain.active_tool is None
    assert client.p2p[-1]["msg_type"] == "proposal"
    assert client.p2p[-1]["content"]["kind"] == "deliberation"
    assert client.p2p[-1]["content"]["phase"] == "proposal"


@pytest.mark.anyio
async def test_deliberation_acks_compatible_peer_and_commits() -> None:
    client = FakeClient()
    brain = make_brain(client)
    obs = make_obs()

    brain.view.tick(obs.world_time)
    brain.view.peers["agent_1"] = PeerInfo(agent_id="agent_1", lat=37.54, lon=15.22, updated_t=obs.world_time)
    brain._start_deliberation("mission", obs)
    assert brain._deliberation is not None
    session = brain._deliberation
    session.record_proposal(Proposal("agent_0", "search_area", {"sector": "NW", "priority": "speed"}, "own", 1))
    session.record_proposal(Proposal("agent_1", "search_area", {"sector": "SE", "priority": "speed"}, "peer", 1))

    await brain._advance_deliberation(obs, FixedDecider().decide(), "")

    assert any(msg["msg_type"] == "ack" and msg["content"]["phase"] == "ack" for msg in client.p2p)
    assert not any(msg["msg_type"] == "ack" and msg["content"]["phase"] == "commit" for msg in client.p2p)
    assert brain._deliberation is not None
    assert brain.active_tool is None

    await brain._advance_deliberation(later_obs(7.0), FixedDecider().decide(), "")

    assert any(msg["msg_type"] == "ack" and msg["content"]["phase"] == "commit" for msg in client.p2p)
    assert brain._deliberation is None
    assert brain.active_tool is not None


@pytest.mark.anyio
async def test_deliberation_objects_to_conflict_then_falls_back() -> None:
    client = FakeClient()
    brain = make_brain(client)
    obs = make_obs()

    brain.view.tick(obs.world_time)
    brain.view.peers["agent_1"] = PeerInfo(agent_id="agent_1", lat=37.54, lon=15.22, updated_t=obs.world_time)
    brain._start_deliberation("mission", obs)
    assert brain._deliberation is not None
    session = brain._deliberation
    session.record_proposal(Proposal("agent_0", "search_area", {"sector": "NW", "priority": "speed"}, "own", 1))
    session.record_proposal(Proposal("agent_1", "search_area", {"sector": "NW", "priority": "speed"}, "peer", 1))

    await brain._advance_deliberation(obs, FixedDecider().decide(), "")

    objection = next(msg for msg in client.p2p if msg["msg_type"] == "objection")
    assert objection["to"] == "all"
    assert objection["content"]["target"] == "agent_1"
    assert brain._deliberation is not None

    brain._deliberation.round = brain._deliberation.max_rounds
    await brain._advance_deliberation(later_obs(7.0), FixedDecider().decide(), "")

    assert brain._deliberation is None
    assert any(msg["msg_type"] == "ack" and msg["content"]["phase"] == "commit" for msg in client.p2p)
    commit = next(msg for msg in reversed(client.p2p) if msg["content"].get("phase") == "commit")
    sectors = [
        spec["args"]["sector"]
        for spec in commit["content"]["plan"].values()
        if spec["tool"] == "search_area"
    ]
    assert len(sectors) == len(set(sectors))
    assert "NW" in sectors


@pytest.mark.anyio
async def test_deliberation_commit_deconflicts_broad_overlapping_sectors() -> None:
    client = FakeClient()
    brain = make_brain(client)
    obs = make_obs()

    brain.view.tick(obs.world_time)
    brain.view.peers["agent_1"] = PeerInfo(agent_id="agent_1", lat=37.46, lon=15.08, updated_t=obs.world_time)
    brain.view.peers["agent_2"] = PeerInfo(agent_id="agent_2", lat=37.56, lon=15.09, updated_t=obs.world_time)
    brain._start_deliberation("mission", obs)
    assert brain._deliberation is not None
    session = brain._deliberation
    session.record_proposal(Proposal("agent_0", "search_area", {"sector": "WEST", "priority": "speed"}, "own", 1))
    session.record_proposal(Proposal("agent_1", "search_area", {"sector": "SW", "priority": "speed"}, "peer", 1))
    session.record_proposal(Proposal("agent_2", "search_area", {"sector": "WEST", "priority": "coverage"}, "peer", 1))
    session.round = session.max_rounds

    await brain._advance_deliberation(later_obs(7.0), FixedDecider().decide(), "")

    assert brain._deliberation is None
    commit = next(msg for msg in reversed(client.p2p) if msg["content"].get("phase") == "commit")
    sectors = [
        spec["args"]["sector"]
        for spec in commit["content"]["plan"].values()
        if spec["tool"] == "search_area"
    ]
    assert len(sectors) == 3
    assert len(sectors) == len(set(sectors))
    assert "WEST" not in sectors
