from __future__ import annotations
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from engine.connection_manager import manager

router = APIRouter()


@router.websocket("/frontend")
async def frontend_ws(ws: WebSocket) -> None:
    await manager.connect_frontend(ws)
    try:
        while True:
            # Keep connection alive; frontend only receives, never sends
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_frontend(ws)
