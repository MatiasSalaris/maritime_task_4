"""Tests for the AI control layer: grounded tools, coordination, planners.

Fully deterministic — no network or LLM.
"""

from __future__ import annotations

import pytest

from maritime_swarm.ai_control import coordination as coord
from maritime_swarm.ai_control.blackboard import SwarmView
from maritime_swarm.ai_control.geo import bearing_deg, haversine_km
from maritime_swarm.ai_control.navigation_tools import (
    EscortContactTool,
    GoToPoiTool,
    InvestigateContactTool,
    PatrolSectorTool,
    ReportContactTool,
    VisitPoisTool,
    default_registry,
)
from maritime_swarm.ai_control.observation import Observation, SensedContact
from maritime_swarm.ai_control.planner import HeuristicTactician
from maritime_swarm.ai_control.scene import POI, Scene
from maritime_swarm.ai_control.strategist import HeuristicStrategist
from maritime_swarm.ai_control.tools import Bounds, ToolContext, ToolError, ToolStatus

BOUNDS = Bounds(lat_min=37.42, lat_max=37.60, lon_min=15.00, lon_max=15.28)
SCENE = Scene(bounds=BOUNDS, pois=[POI("poi_1", "Alpha", 37.55, 15.22), POI("poi_2", "Bravo", 37.45, 15.06)])


def make_obs(lat, lon, contacts=None):
    return Observation(agent_id="agent_0", lat=lat, lon=lon, heading=0.0, speed_kn=0.0,
                       contacts=contacts or [], world_time=1000.0, mission="patrol")


def make_ctx(obs=None, view=None, scene=SCENE):
    return ToolContext(agent_id="agent_0", agent_name="Alpha", agent_type="USV",
                       cruise_speed_kn=28.0, arrival_km=0.3, bounds=BOUNDS,
                       obs=obs, view=view, scene=scene)


# ── geo ────────────────────────────────────────────────────────────────────────
def test_bearing_cardinal():
    assert bearing_deg(37.5, 15.1, 37.6, 15.1) == pytest.approx(0.0, abs=1.0)
    assert bearing_deg(37.5, 15.1, 37.5, 15.2) == pytest.approx(90.0, abs=1.0)
    assert bearing_deg(37.5, 15.1, 37.4, 15.1) == pytest.approx(180.0, abs=1.0)


# ── grounding ───────────────────────────────────────────────────────────────────
def test_investigate_requires_known_contact():
    obs = make_obs(37.5, 15.1, [])
    with pytest.raises(ToolError):
        InvestigateContactTool.build({"contact_id": "ghost"}, make_ctx(obs=obs))


def test_investigate_accepts_sensed_contact():
    c = SensedContact(id="c003", lat=37.52, lon=15.12, flagged=True)
    obs = make_obs(37.5, 15.1, [c])
    tool = InvestigateContactTool.build({"contact_id": "c003"}, make_ctx(obs=obs))
    inv = tool.step(obs, make_ctx(obs=obs))
    assert inv.status is ToolStatus.RUNNING
    assert inv.action["speed_kn"] == 28.0


def test_investigate_accepts_shared_contact_not_in_range():
    view = SwarmView("agent_0")
    view.tick(1000.0)
    view.ingest("agent_1", "status", {"contacts": [{"id": "c003", "lat": 37.52, "lon": 15.12, "flagged": True}]})
    obs = make_obs(37.5, 15.1, [])
    tool = InvestigateContactTool.build({"contact_id": "c003"}, make_ctx(obs=obs, view=view))
    assert isinstance(tool, InvestigateContactTool)


def test_go_to_poi_grounded():
    obs = make_obs(37.5, 15.1)
    tool = GoToPoiTool.build({"poi_id": "poi_1"}, make_ctx(obs=obs))
    assert (tool.lat, tool.lon) == (37.55, 15.22)
    with pytest.raises(ToolError):
        GoToPoiTool.build({"poi_id": "nope"}, make_ctx(obs=obs))


def test_report_contact_emits_p2p():
    c = SensedContact(id="c003", lat=37.5, lon=15.1, flagged=True)
    obs = make_obs(37.5, 15.1, [c])
    tool = ReportContactTool.build(
        {"contact_id": "c003", "classification": "anomaly", "rationale": "no AIS, high speed"},
        make_ctx(obs=obs))
    inv = tool.step(obs, make_ctx(obs=obs))
    assert inv.status is ToolStatus.DONE
    assert inv.p2p is not None
    assert inv.p2p["msg_type"] == "report"
    assert inv.p2p["content"]["report"]["classification"] == "ANOMALY"
    assert inv.p2p["content"]["contacts"][0]["reported"] is True


def test_patrol_sector_runs_forever_and_advances():
    tool = PatrolSectorTool.build({"sector": "NE"}, make_ctx())
    obs = make_obs(37.5, 15.1)
    inv = tool.step(obs, make_ctx(obs=obs))
    assert inv.status is ToolStatus.RUNNING
    assert tool.sector == "NE"
    with pytest.raises(ToolError):
        PatrolSectorTool.build({"sector": "MIDDLE"}, make_ctx())


def test_escort_holds_standoff():
    c = SensedContact(id="c001", lat=37.50, lon=15.10)
    obs = make_obs(37.50, 15.10, [c])
    tool = EscortContactTool.build({"contact_id": "c001", "standoff_m": 500, "bearing_deg": 90}, make_ctx(obs=obs))
    inv = tool.step(obs, make_ctx(obs=obs))
    assert inv.status is ToolStatus.RUNNING  # escort never completes
    # station is offset east of the contact → agent should be steered, not stopped
    assert inv.action is not None


def test_visit_pois_sequences():
    obs = make_obs(37.55, 15.22)  # at poi_1
    tool = VisitPoisTool.build({"poi_ids": ["poi_1", "poi_2"]}, make_ctx(obs=obs))
    inv = tool.step(obs, make_ctx(obs=obs))   # reaches poi_1, advances
    assert inv.status is ToolStatus.RUNNING
    assert tool._idx == 1


# ── coordination ────────────────────────────────────────────────────────────────
def test_sectors_distinct_centers():
    centers = {s: coord.sector_center(BOUNDS, s) for s in coord.SECTORS}
    assert len(set(centers.values())) == len(coord.SECTORS)


def test_default_allocation_spreads_sectors():
    alloc = coord.default_allocation(["agent_0", "agent_1", "agent_2"], BOUNDS)
    sectors = {a["sector"] for a in alloc.values()}
    assert len(sectors) == 3  # three distinct sectors


def test_deconflict_resolves_duplicate_sector():
    # two agents both claim NE → must end on different sectors
    alloc = {
        "agent_0": {"kind": "patrol_sector", "sector": "NE"},
        "agent_1": {"kind": "patrol_sector", "sector": "NE"},
    }
    positions = {"agent_0": (37.59, 15.27), "agent_1": (37.43, 15.01)}  # a0 near NE, a1 far
    out = coord.deconflict(alloc, ["agent_0", "agent_1"], positions, BOUNDS)
    assert out["agent_0"]["sector"] == "NE"          # closer keeps it
    assert out["agent_1"]["sector"] != "NE"          # loser reassigned


def test_deconflict_preserves_non_patrol():
    alloc = {"agent_0": {"kind": "escort", "contact_id": "c1", "standoff_m": 500, "bearing_deg": 0}}
    out = coord.deconflict(alloc, ["agent_0"], {"agent_0": (37.5, 15.1)}, BOUNDS)
    assert out["agent_0"]["kind"] == "escort"


def test_assignment_label():
    assert coord.assignment_label({"kind": "patrol_sector", "sector": "NE"}) == "PATROL NE"
    assert "ESCORT" in coord.assignment_label({"kind": "escort", "contact_id": "c1", "standoff_m": 500})
    assert coord.assignment_label(None) == "UNASSIGNED"


# ── shared picture ────────────────────────────────────────────────────────────────
def test_swarmview_ingest_status_and_silence():
    v = SwarmView("agent_0")
    v.tick(100.0)
    v.ingest("agent_1", "status", {"name": "Bravo", "pos": {"lat": 37.5, "lon": 15.1},
                                    "contacts": [{"id": "c1", "lat": 37.5, "lon": 15.1, "label": "UNKNOWN"}]})
    assert "agent_1" in v.peers
    assert "c1" in v.contacts
    assert v.live_peer_ids() == ["agent_1"]
    v.tick(100.0 + 999)  # long after → silent
    assert v.silent_peer_ids() == ["agent_1"]


def test_swarmview_ingest_proposal_sets_allocation():
    v = SwarmView("agent_0")
    v.tick(10.0)
    v.ingest("agent_1", "proposal", {"brief": {"objective": "patrol"},
                                     "allocation": {"agent_0": {"kind": "patrol_sector", "sector": "SW"}}})
    assert v.my_assignment() == {"kind": "patrol_sector", "sector": "SW"}
    assert v.brief["objective"] == "patrol"


# ── planners (offline) ───────────────────────────────────────────────────────────
def test_heuristic_strategist_allocates_all():
    members = [{"id": "agent_0"}, {"id": "agent_1"}, {"id": "agent_2"}]
    plan = HeuristicStrategist().plan("patrol the area", members, SCENE, [])
    assert set(plan["allocation"]) == {"agent_0", "agent_1", "agent_2"}
    assert all(a["kind"] == "patrol_sector" for a in plan["allocation"].values())


def test_heuristic_tactician_investigates_then_reports():
    tac = HeuristicTactician()
    far = SensedContact(id="c003", lat=37.56, lon=15.18, flagged=True)
    near = SensedContact(id="c003", lat=37.5005, lon=15.1005, flagged=True)
    ctx = make_ctx()
    d_far = tac.decide_reactive(make_obs(37.5, 15.1, [far]), ctx, "m", None, "PATROL NE", [])
    assert d_far["action"] == "investigate"
    d_near = tac.decide_reactive(make_obs(37.5, 15.1, [near]), ctx, "m", None, "PATROL NE", [])
    assert d_near["action"] == "report"


def test_heuristic_tactician_follows_on_follow_mission():
    tac = HeuristicTactician()
    near = SensedContact(id="c003", lat=37.5005, lon=15.1005, flagged=True)
    mission = "scan the area and find any unreported vessel. follow it at 500m distance"
    d = tac.decide_reactive(make_obs(37.5, 15.1, [near]), make_ctx(), mission, None, "PATROL NE", [])
    assert d["action"] == "escort"
    assert d["contact_id"] == "c003"
    # and on a report-only mission it reports instead
    d2 = tac.decide_reactive(make_obs(37.5, 15.1, [near]), make_ctx(), "report anomalies", None, "PATROL NE", [])
    assert d2["action"] == "report"


def test_registry_has_full_toolset():
    names = set(default_registry().names())
    assert {"go_to", "go_to_poi", "patrol_sector", "investigate_contact",
            "report_contact", "escort_contact", "visit_pois", "rendezvous", "hold_position"} <= names
