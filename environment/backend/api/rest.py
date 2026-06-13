from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from engine import app_state
from engine.message_bus import message_bus

router = APIRouter()


class MissionPayload(BaseModel):
    text: str


class MissionCompletePayload(BaseModel):
    result: dict


class AgentStatusPayload(BaseModel):
    status: str  # "operational" | "degraded" | "silent"


class ContactPositionPayload(BaseModel):
    lat: float
    lon: float


@router.post("/mission")
async def set_mission(body: MissionPayload) -> dict:
    await app_state.engine.provider.set_mission(body.text)
    return {"ok": True, "mission": body.text}


@router.post("/mission/change")
async def change_mission(body: MissionPayload) -> dict:
    """Mid-mission intent change — same as set_mission but semantically distinct."""
    await app_state.engine.provider.set_mission(body.text)
    return {"ok": True, "mission": body.text}


@router.post("/mission/complete")
async def complete_mission(body: MissionCompletePayload) -> dict:
    await app_state.engine.provider.complete_mission(body.result)
    return {"ok": True, "mission_status": "completed", "result": body.result}


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


@router.post("/contacts/{contact_id}/position")
async def set_contact_position(contact_id: str, body: ContactPositionPayload) -> dict:
    ok = await app_state.engine.provider.set_contact_position(contact_id, body.lat, body.lon)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Contact {contact_id} not found")
    return {"ok": True, "contact_id": contact_id, "lat": body.lat, "lon": body.lon}


@router.post("/reset")
async def reset_sim() -> dict:
    """Clear all path history, CoT, tasks, mission, and message log. Call before each demo run."""
    await app_state.engine.provider.reset()
    message_bus.clear()
    return {"ok": True}


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
