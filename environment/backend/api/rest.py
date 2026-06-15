from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from engine import app_state
from engine.connection_manager import manager
from engine.message_bus import message_bus

router = APIRouter()


class MissionPayload(BaseModel):
    text: str


class AgentStatusPayload(BaseModel):
    status: str  # "operational" | "degraded" | "silent"


@router.post("/mission")
async def set_mission(body: MissionPayload) -> dict:
    await app_state.engine.provider.set_mission(body.text)
    app_state.engine.paused = False  # a new order resumes a paused (post-reset) world
    return {"ok": True, "mission": body.text}


@router.post("/mission/change")
async def change_mission(body: MissionPayload) -> dict:
    """Mid-mission intent change — same as set_mission but semantically distinct."""
    await app_state.engine.provider.set_mission(body.text)
    app_state.engine.paused = False
    return {"ok": True, "mission": body.text}


class ScenarioPayload(BaseModel):
    id: str


@router.get("/scenarios")
async def get_scenarios() -> dict:
    from providers.simulation.scenarios import list_scenarios
    return {"scenarios": list_scenarios()}


@router.post("/scenario")
async def load_scenario(body: ScenarioPayload) -> dict:
    """Switch the world to a scenario: wipe agents, rebuild the world, set its
    mission, and resume. The lead asset then briefs the peers on the new intent."""
    engine = app_state.engine
    engine.paused = True
    for agent_id in manager.connected_agent_ids():
        await manager.send_to_agent(agent_id, {"type": "reset"})
    result = await engine.provider.load_scenario(body.id)
    message_bus.clear()
    engine.paused = False
    return {"ok": True, **result}


class SpeedPayload(BaseModel):
    scale: float  # sim-time multiplier, e.g. 0.5, 1, 2, 4


@router.post("/speed")
async def set_speed(body: SpeedPayload) -> dict:
    """Set the simulation speed multiplier (clamped to a sane range)."""
    scale = max(0.25, min(8.0, body.scale))
    app_state.engine.time_scale = scale
    return {"ok": True, "scale": scale}


@router.get("/state")
async def get_state() -> dict:
    state = await app_state.engine.provider.get_world_state()
    return state.model_dump()


@router.get("/messages")
async def get_messages(n: int = 100) -> dict:
    return {"messages": message_bus.log_dicts(n)}


class DoctrinePayload(BaseModel):
    code: str  # PHASE0 | PHASE1 | MSO | PHASE2 | PHASE3


class AORPayload(BaseModel):
    geometry: dict | None = None  # GeoJSON Polygon or None to clear


@router.post("/doctrine")
async def set_doctrine(body: DoctrinePayload) -> dict:
    await app_state.engine.provider.set_doctrine(body.code)
    return {"ok": True, "doctrine": body.code}


@router.post("/aor")
async def set_aor(body: AORPayload) -> dict:
    await app_state.engine.provider.set_aor(body.geometry)
    return {"ok": True}


@router.post("/reset")
async def reset_sim() -> dict:
    """Full wipe — back to a just-booted state. Resets the world (spawn poses,
    contacts, mission, CoT), clears the message bus, freezes the engine, and
    tells every AI agent to wipe its in-memory state (mission, shared picture,
    active task, outbox) so nothing from the previous run lingers."""
    app_state.engine.paused = True
    for agent_id in manager.connected_agent_ids():
        await manager.send_to_agent(agent_id, {"type": "reset"})
    await app_state.engine.provider.reset()
    message_bus.clear()
    return {"ok": True, "paused": True}


@router.post("/agents/{agent_id}/status")
async def set_agent_status(agent_id: str, body: AgentStatusPayload) -> dict:
    """Force-set an agent's status (e.g., simulate comm disruption)."""
    from models.agent import AgentStatus
    provider = app_state.engine.provider
    state = await provider.get_world_state()
    agent = next((a for a in state.agents if a.id == agent_id), None)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    try:
        agent.status = AgentStatus(body.status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {body.status}")
    return {"ok": True, "agent_id": agent_id, "status": body.status}
