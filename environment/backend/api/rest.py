from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from engine import app_state
from engine.message_bus import message_bus

router = APIRouter()


class MissionPayload(BaseModel):
    text: str


class AgentStatusPayload(BaseModel):
    status: str  # "operational" | "degraded" | "silent"


@router.post("/mission")
async def set_mission(body: MissionPayload) -> dict:
    await app_state.engine.provider.set_mission(body.text)
    return {"ok": True, "mission": body.text}


@router.post("/mission/change")
async def change_mission(body: MissionPayload) -> dict:
    """Mid-mission intent change — same as set_mission but semantically distinct."""
    await app_state.engine.provider.set_mission(body.text)
    return {"ok": True, "mission": body.text}


@router.get("/state")
async def get_state() -> dict:
    state = await app_state.engine.provider.get_world_state()
    return state.model_dump()


@router.get("/messages")
async def get_messages(n: int = 100) -> dict:
    return {"messages": message_bus.log_dicts(n)}


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
