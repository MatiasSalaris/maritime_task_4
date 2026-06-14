"""Tests for the AI control layer: grounded tools, the open-ended decider,
the shared picture, and coordination helpers. Deterministic — no network/LLM.
"""

from __future__ import annotations

import pytest

from maritime_swarm.ai_control import coordination as coord
from maritime_swarm.ai_control.blackboard import SwarmView
from maritime_swarm.ai_control.geo import bearing_deg, destination, haversine_km
from maritime_swarm.ai_control.message_constraints import P2P_TEXT_MAX_CHARS
from maritime_swarm.ai_control.navigation_tools import (
    EscortContactTool,
    GoToPoiTool,
    InvestigateContactTool,
    MoveTool,
    PatrolSectorTool,
    ReportContactTool,
    SearchAreaTool,
    VisitPoisTool,
    default_registry,
)
from maritime_swarm.ai_control.observation import Observation, SensedContact
from maritime_swarm.ai_control.planner import HeuristicDecider, normalise_decision
from maritime_swarm.ai_control.scene import POI, Scene
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


def test_destination_south():
    lat, lon = destination(37.5, 15.1, 180, 5)   # 5 km south
    assert lat == pytest.approx(37.5 - 5 / 111.32, abs=1e-4)
    assert lon == pytest.approx(15.1, abs=1e-6)


# ── grounding ───────────────────────────────────────────────────────────────────
def test_investigate_requires_known_contact():
    with pytest.raises(ToolError):
        InvestigateContactTool.build({"contact_id": "ghost"}, make_ctx(obs=make_obs(37.5, 15.1, [])))


def test_investigate_accepts_sensed_or_shared():
    c = SensedContact(id="c003", lat=37.52, lon=15.12, flagged=True)
    InvestigateContactTool.build({"contact_id": "c003"}, make_ctx(obs=make_obs(37.5, 15.1, [c])))
    v = SwarmView("agent_0"); v.tick(1000.0)
    v.ingest("agent_1", "status", {"contacts": [{"id": "c9", "lat": 37.5, "lon": 15.1, "flagged": True}]})
    InvestigateContactTool.build({"contact_id": "c9"}, make_ctx(obs=make_obs(37.5, 15.1, []), view=v))


def test_go_to_poi_grounded():
    GoToPoiTool.build({"poi_id": "poi_1"}, make_ctx(obs=make_obs(37.5, 15.1)))
    with pytest.raises(ToolError):
        GoToPoiTool.build({"poi_id": "nope"}, make_ctx(obs=make_obs(37.5, 15.1)))


def test_report_emits_p2p():
    c = SensedContact(id="c003", lat=37.5, lon=15.1, flagged=True)
    tool = ReportContactTool.build(
        {"contact_id": "c003", "classification": "anomaly", "rationale": "no AIS"}, make_ctx(obs=make_obs(37.5, 15.1, [c])))
    inv = tool.step(make_obs(37.5, 15.1, [c]), make_ctx(obs=make_obs(37.5, 15.1, [c])))
    assert inv.status is ToolStatus.DONE and inv.p2p["msg_type"] == "report"
    assert inv.p2p["content"]["report"]["classification"] == "ANOMALY"


# ── move (relative / directional) ───────────────────────────────────────────────
def test_move_south_targets_south():
    obs = make_obs(37.50, 15.10)
    tool = MoveTool.build({"direction": "south", "distance_km": 5}, make_ctx(obs=obs))
    assert tool.lat < 37.50                       # heading south
    assert tool.lon == pytest.approx(15.10, abs=1e-3)
    inv = tool.step(obs, make_ctx(obs=obs))
    assert inv.status is ToolStatus.RUNNING and inv.action["speed_kn"] == 28.0


def test_move_accepts_bearing_and_clamps():
    obs = make_obs(37.59, 15.27)                  # near NE corner
    tool = MoveTool.build({"direction": "45", "distance_km": 50}, make_ctx(obs=obs))  # NE, far → clamps
    assert tool.lat <= BOUNDS.lat_max and tool.lon <= BOUNDS.lon_max
    with pytest.raises(ToolError):
        MoveTool.build({"direction": "sideways"}, make_ctx(obs=obs))


def test_patrol_and_escort_and_visit_build():
    assert PatrolSectorTool.build({"sector": "NE"}, make_ctx()).sector == "NE"
    c = SensedContact(id="c1", lat=37.5, lon=15.1)
    EscortContactTool.build({"contact_id": "c1", "standoff_m": 500}, make_ctx(obs=make_obs(37.5, 15.1, [c])))
    VisitPoisTool.build({"poi_ids": ["poi_1", "poi_2"]}, make_ctx(obs=make_obs(37.5, 15.1)))


def test_search_area_requires_explicit_cognitive_sector():
    ctx = make_ctx(obs=make_obs(37.5, 15.1))
    with pytest.raises(ToolError):
        SearchAreaTool.build({"sector": "AUTO"}, ctx)
    with pytest.raises(ToolError):
        SearchAreaTool.build({}, ctx)
    assert SearchAreaTool.build({"sector": "NW", "priority": "speed"}, ctx).sector == "NW"


# ── coordination helpers (still used as utilities) ───────────────────────────────
def test_sectors_distinct_centers():
    centers = {coord.sector_center(BOUNDS, s) for s in coord.SECTORS}
    assert len(centers) == len(coord.SECTORS)


def test_assignment_label_covers_kinds():
    assert coord.assignment_label({"kind": "patrol_sector", "sector": "NE"}) == "PATROL NE"
    assert coord.assignment_label({"kind": "go_to", "lat": 37.5, "lon": 15.1}).startswith("PROCEED")
    assert coord.assignment_label(None) == "UNASSIGNED"


# ── shared picture ────────────────────────────────────────────────────────────────
def test_swarmview_status_and_silence():
    v = SwarmView("agent_0"); v.tick(100.0)
    v.ingest("agent_1", "status", {"name": "Bravo", "pos": {"lat": 37.5, "lon": 15.1},
                                   "task": "Patrolling NE",
                                   "contacts": [{"id": "c1", "lat": 37.5, "lon": 15.1, "label": "UNKNOWN"}]})
    assert v.live_peer_ids() == ["agent_1"]
    assert v.peers["agent_1"].task == "Patrolling NE"
    assert "c1" in v.contacts
    v.tick(100.0 + 999)
    assert v.silent_peer_ids() == ["agent_1"]


def test_swarmview_keeps_nl_messages():
    v = SwarmView("agent_0"); v.tick(10.0)
    v.ingest("agent_1", "proposal", {"text": "I'll take the north"}, reasoning="I'll take the north")
    v.ingest("agent_2", "ack", {}, reasoning="Copy — I'll take the south")
    msgs = v.recent_messages()
    assert [m.msg_type for m in msgs] == ["proposal", "ack"]
    assert "north" in msgs[0].text


# ── decider ───────────────────────────────────────────────────────────────────────
def test_normalise_decision_shapes_output():
    d = normalise_decision({
        "reasoning": "x",
        "messages": [{"to": "all", "type": "weird", "content": "hi"}, {"type": "ack", "content": ""}],
        "action": {"tool": "move", "arguments": {"direction": "south"}},
    })
    assert d["tool"] == "move" and d["args"] == {"direction": "south"}
    assert len(d["messages"]) == 1                     # empty-content msg dropped
    assert d["messages"][0]["type"] == "status"        # unknown type coerced


def test_normalise_decision_enforces_telegraphic_message_limit():
    long = "Propongo di cercare nel settore NW perche sono gia molto vicino al quadrante nord occidentale e posso evitare sovrapposizioni con tutti i peer."
    d = normalise_decision({
        "messages": [{"to": "all", "type": "proposal", "content": long}],
        "action": {"tool": "hold_position", "args": {}},
    })
    assert len(d["messages"][0]["content"]) <= P2P_TEXT_MAX_CHARS
    assert "\n" not in d["messages"][0]["content"]


def test_heuristic_decider_runs():
    dec = HeuristicDecider()
    reg = default_registry()
    out = dec.decide(make_obs(37.5, 15.1, []), make_ctx(), SCENE, "patrol the area", [], [], [], None, reg)
    assert out["tool"] == "patrol_sector"
    c = SensedContact(id="c003", lat=37.5, lon=15.1, flagged=True)
    out2 = dec.decide(make_obs(37.5, 15.1, [c]), make_ctx(), SCENE, "patrol", [], [], [], None, reg)
    assert out2["tool"] == "investigate_contact"


def test_decision_prompt_builds_with_full_state():
    # Regression: the outbox carries {to,type,content}; the prompt must not KeyError.
    from maritime_swarm.ai_control.prompts import build_decision_user_prompt
    obs = make_obs(37.5, 15.1, [SensedContact(id="c1", lat=37.5, lon=15.1, flagged=True)])
    p = build_decision_user_prompt(
        obs, make_ctx(obs=obs), SCENE, "patrol and report",
        peers=[{"id": "agent_1", "type": "USV", "lat": 37.49, "lon": 15.16, "task": "Patrolling SE"}],
        shared_contacts=[{"id": "c9", "label": "UNKNOWN", "flagged": True, "reported": False, "lat": 37.5, "lon": 15.2}],
        messages=[{"sender": "agent_1", "type": "proposal", "text": "I'll take SE"}],
        current_task="Patrolling NW", task_status="executing", silent_peers=["agent_2"],
        outbox=[{"to": "all", "type": "ack", "content": "Copy, I take NW"}],
    )
    assert "Patrolling NW" in p and "SILENT" in p and "Copy, I take NW" in p and "c1" in p


def test_registry_has_full_toolset():
    names = set(default_registry().names())
    assert {"go_to", "move", "go_to_poi", "patrol_sector", "investigate_contact",
            "report_contact", "escort_contact", "visit_pois", "rendezvous", "hold_position"} <= names
