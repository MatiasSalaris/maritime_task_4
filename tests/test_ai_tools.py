"""Tests for the AI control layer's Tool abstraction and planners.

These are fully deterministic — no network or LLM is involved.
"""

from __future__ import annotations

import math

import pytest

from maritime_swarm.ai_control.geo import bearing_deg, haversine_km
from maritime_swarm.ai_control.observation import Observation, SensedContact
from maritime_swarm.ai_control.navigation_tools import (
    GoToTool,
    HoldPositionTool,
    InvestigateContactTool,
    default_registry,
)
from maritime_swarm.ai_control.planner import HeuristicPlanner
from maritime_swarm.ai_control.scene import POI, Scene
from maritime_swarm.ai_control.tools import Bounds, ToolContext, ToolError, ToolStatus


BOUNDS = Bounds(lat_min=37.42, lat_max=37.60, lon_min=15.00, lon_max=15.28)


def make_ctx(agent_id: str = "agent_0", agent_type: str = "USV") -> ToolContext:
    return ToolContext(
        agent_id=agent_id,
        agent_name="Alpha",
        agent_type=agent_type,
        cruise_speed_kn=28.0,
        arrival_km=0.3,
        bounds=BOUNDS,
    )


def make_obs(lat: float, lon: float, contacts: list[SensedContact] | None = None) -> Observation:
    return Observation(
        agent_id="agent_0",
        lat=lat,
        lon=lon,
        heading=0.0,
        speed_kn=0.0,
        contacts=contacts or [],
        world_time=1000.0,
        mission="patrol",
    )


# ── geo ──────────────────────────────────────────────────────────────────────
def test_bearing_cardinal_directions():
    # Due north, east, south, west from a reference point.
    assert bearing_deg(37.5, 15.1, 37.6, 15.1) == pytest.approx(0.0, abs=1.0)
    assert bearing_deg(37.5, 15.1, 37.5, 15.2) == pytest.approx(90.0, abs=1.0)
    assert bearing_deg(37.5, 15.1, 37.4, 15.1) == pytest.approx(180.0, abs=1.0)
    assert bearing_deg(37.5, 15.1, 37.5, 15.0) == pytest.approx(270.0, abs=1.0)


def test_haversine_known_distance():
    # ~0.1 deg latitude ≈ 11.12 km
    assert haversine_km(37.5, 15.1, 37.6, 15.1) == pytest.approx(11.12, abs=0.2)


# ── go_to ─────────────────────────────────────────────────────────────────────
def test_go_to_steers_then_arrives():
    tool = GoToTool.build({"lat": 37.55, "lon": 15.20}, make_ctx())

    far = tool.step(make_obs(37.50, 15.10), make_ctx())
    assert far.status is ToolStatus.RUNNING
    assert far.action["speed_kn"] == 28.0
    # Heading should point roughly north-east toward the target.
    assert 0.0 < far.action["heading"] < 90.0
    assert far.action["planned_path"] == [{"lat": 37.55, "lon": 15.20}]

    arrived = tool.step(make_obs(37.5500, 15.2000), make_ctx())
    assert arrived.status is ToolStatus.DONE
    assert arrived.action["speed_kn"] == 0.0


def test_go_to_clamps_target_into_bounds():
    tool = GoToTool.build({"lat": 99.0, "lon": 99.0}, make_ctx())
    assert tool.lat <= BOUNDS.lat_max
    assert tool.lon <= BOUNDS.lon_max
    assert tool.lat >= BOUNDS.lat_min
    assert tool.lon >= BOUNDS.lon_min


def test_go_to_rejects_missing_args():
    with pytest.raises(ToolError):
        GoToTool.build({"lat": 37.5}, make_ctx())
    with pytest.raises(ToolError):
        GoToTool.build({"lat": "north", "lon": 15.0}, make_ctx())


# ── investigate_contact ────────────────────────────────────────────────────────
def test_investigate_tracks_and_reaches_contact():
    contact = SensedContact(id="c003", lat=37.52, lon=15.12, label="UNKNOWN", flagged=True)
    tool = InvestigateContactTool.build({"contact_id": "c003"}, make_ctx())

    running = tool.step(make_obs(37.50, 15.10, [contact]), make_ctx())
    assert running.status is ToolStatus.RUNNING
    assert running.action["speed_kn"] == 28.0

    reached = tool.step(make_obs(37.5200, 15.1200, [contact]), make_ctx())
    assert reached.status is ToolStatus.DONE


def test_investigate_fails_when_contact_never_seen():
    tool = InvestigateContactTool.build({"contact_id": "ghost"}, make_ctx())
    result = tool.step(make_obs(37.50, 15.10, []), make_ctx())
    assert result.status is ToolStatus.FAILED
    assert result.action is None


def test_investigate_uses_last_known_when_contact_drops_out():
    contact = SensedContact(id="c003", lat=37.52, lon=15.12, flagged=True)
    tool = InvestigateContactTool.build({"contact_id": "c003"}, make_ctx())
    tool.step(make_obs(37.50, 15.10, [contact]), make_ctx())  # sees it once
    # Next tick: contact no longer sensed → keep heading to last known pos.
    dropped = tool.step(make_obs(37.505, 15.105, []), make_ctx())
    assert dropped.status is ToolStatus.RUNNING


# ── hold_position ──────────────────────────────────────────────────────────────
def test_hold_position_runs_then_completes():
    tool = HoldPositionTool.build({"seconds": 10}, make_ctx())
    start = tool.step(make_obs(37.5, 15.1), make_ctx())
    assert start.status is ToolStatus.RUNNING
    assert start.action["speed_kn"] == 0.0

    obs_later = make_obs(37.5, 15.1)
    obs_later.world_time = 1011.0  # 11s later
    done = tool.step(obs_later, make_ctx())
    assert done.status is ToolStatus.DONE


def test_hold_seconds_clamped():
    assert HoldPositionTool.build({"seconds": 9999}, make_ctx()).seconds == 120.0
    assert HoldPositionTool.build({}, make_ctx()).seconds == 20.0


# ── registry ───────────────────────────────────────────────────────────────────
def test_registry_builds_known_tool_and_rejects_unknown():
    reg = default_registry()
    assert set(reg.names()) == {"go_to", "investigate_contact", "hold_position"}
    tool = reg.build("go_to", {"lat": 37.5, "lon": 15.1}, make_ctx())
    assert isinstance(tool, GoToTool)
    with pytest.raises(ToolError):
        reg.build("self_destruct", {}, make_ctx())


def test_registry_prompt_block_documents_tools():
    block = default_registry().prompt_block()
    assert "go_to(lat, lon)" in block
    assert "investigate_contact(contact_id)" in block
    assert "hold_position(seconds)" in block


# ── heuristic planner ──────────────────────────────────────────────────────────
def test_heuristic_investigates_suspicious_contact():
    scene = Scene(bounds=BOUNDS, pois=[POI("poi_1", "A", 37.55, 15.22)])
    planner = HeuristicPlanner()
    contact = SensedContact(id="c003", lat=37.51, lon=15.11, label="UNKNOWN", flagged=True)
    decision = planner.decide(make_obs(37.5, 15.1, [contact]), make_ctx(), scene, "m", default_registry())
    assert decision["tool"] == "investigate_contact"
    assert decision["args"]["contact_id"] == "c003"


def test_heuristic_patrols_when_no_contacts():
    scene = Scene(bounds=BOUNDS, pois=[POI("poi_1", "A", 37.55, 15.22)])
    planner = HeuristicPlanner()
    decision = planner.decide(make_obs(37.5, 15.1, []), make_ctx(), scene, "m", default_registry())
    assert decision["tool"] == "go_to"
    assert "lat" in decision["args"] and "lon" in decision["args"]


def test_heuristic_decision_is_executable_by_registry():
    """End-to-end glue: a planner decision must build into a runnable tool."""
    scene = Scene(bounds=BOUNDS, pois=[])
    planner = HeuristicPlanner()
    ctx = make_ctx()
    decision = planner.decide(make_obs(37.5, 15.1, []), ctx, scene, "m", default_registry())
    tool = default_registry().build(decision["tool"], decision["args"], ctx)
    inv = tool.step(make_obs(37.5, 15.1), ctx)
    assert inv.status in (ToolStatus.RUNNING, ToolStatus.DONE)
