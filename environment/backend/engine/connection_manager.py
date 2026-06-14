from __future__ import annotations
import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._frontend: list[WebSocket] = []
        self._agents: dict[str, WebSocket] = {}   # agent_id -> ws

    # ── Frontend connections ──────────────────────────────────────────────

    async def connect_frontend(self, ws: WebSocket) -> None:
        await ws.accept()
        self._frontend.append(ws)
        logger.info("Frontend connected (%d total)", len(self._frontend))

    def disconnect_frontend(self, ws: WebSocket) -> None:
        # Idempotent: broadcast() may have already pruned a dead socket, and the
        # handler's finally-block also calls this — guard against double-remove
        # (a bare list.remove would raise ValueError and, from broadcast(), kill
        # the engine loop).
        if ws in self._frontend:
            self._frontend.remove(ws)
            logger.info("Frontend disconnected (%d remaining)", len(self._frontend))

    async def broadcast(self, data: dict) -> None:
        dead = []
        for ws in list(self._frontend):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect_frontend(ws)

    # ── Agent connections ─────────────────────────────────────────────────

    async def connect_agent(self, agent_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._agents[agent_id] = ws
        logger.info("Agent %s connected", agent_id)

    def disconnect_agent(self, agent_id: str) -> None:
        self._agents.pop(agent_id, None)
        logger.info("Agent %s disconnected", agent_id)

    async def send_to_agent(self, agent_id: str, data: dict) -> bool:
        ws = self._agents.get(agent_id)
        if ws is None:
            return False
        try:
            await ws.send_json(data)
            return True
        except Exception:
            self.disconnect_agent(agent_id)
            return False

    def connected_agent_ids(self) -> list[str]:
        return list(self._agents.keys())

    def is_agent_connected(self, agent_id: str) -> bool:
        return agent_id in self._agents


# Module-level singleton — import this everywhere
manager = ConnectionManager()
