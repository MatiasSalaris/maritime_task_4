from __future__ import annotations
import logging
import uuid
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from engine.connection_manager import manager
from engine.message_bus import message_bus
from engine import app_state
from models.messages import P2PMessage, MessageType

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/agent/{agent_id}")
async def agent_ws(ws: WebSocket, agent_id: str) -> None:
    await manager.connect_agent(agent_id, ws)
    provider = app_state.engine.provider
    await provider.set_agent_connected(agent_id, True)

    all_ids = [a.id for a in (await provider.get_world_state()).agents]

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")

            if msg_type == "action":
                await provider.apply_action(agent_id, data.get("payload", {}))

            elif msg_type == "mission_complete":
                payload = data.get("payload", {}) or {}
                result = payload.get("result", {}) if isinstance(payload, dict) else {}
                result.setdefault("completed_by", agent_id)
                result.setdefault("completed_at", time.time())
                await provider.complete_mission(result)

            elif msg_type == "p2p_message":
                payload = data.get("payload", {})
                message = P2PMessage(
                    id=str(uuid.uuid4()),
                    from_agent=agent_id,
                    to_agent=payload.get("to", "all"),
                    msg_type=MessageType(payload.get("msg_type", "status")),
                    content=payload.get("content", {}),
                    reasoning=payload.get("reasoning"),
                    sent_at=time.time(),
                )
                message_bus.route(message, all_ids)
                # Push immediately to frontend for animation
                await manager.broadcast({
                    "type": "p2p_message",
                    "payload": message.model_dump(),
                })

            elif msg_type == "cot_chunk":
                chunk = data.get("payload", {}).get("chunk", "")
                await provider.update_agent_cot(agent_id, chunk)
                # Stream directly to frontend (don't wait for next tick)
                await manager.broadcast({
                    "type": "cot_chunk",
                    "agent_id": agent_id,
                    "chunk": chunk,
                })

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect_agent(agent_id)
        await provider.set_agent_connected(agent_id, False)
        logger.info("Agent %s disconnected", agent_id)
