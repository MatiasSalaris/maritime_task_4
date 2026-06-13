"""Async WebSocket client to the world model's agent endpoint.

Connects to ``{base_ws}/ws/agent/{agent_id}``, receives observation messages,
and sends actions / chain-of-thought back. This is the *only* coupling point
to the world model, and it speaks the model's documented message contract.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import websockets

logger = logging.getLogger(__name__)


class WorldModelClient:
    def __init__(self, base_ws: str, agent_id: str) -> None:
        self.agent_id = agent_id
        self.url = f"{base_ws.rstrip('/')}/ws/agent/{agent_id}"
        self._ws: Any = None

    async def connect(self) -> None:
        self._ws = await websockets.connect(self.url, max_queue=None, ping_interval=20)
        logger.info("[%s] connected to %s", self.agent_id, self.url)

    async def recv(self) -> dict[str, Any]:
        """Receive and decode the next message from the world model."""
        raw = await self._ws.recv()
        return json.loads(raw)

    async def send_action(self, payload: dict[str, Any]) -> None:
        await self._send({"type": "action", "payload": payload})

    async def send_cot(self, chunk: str) -> None:
        """Stream a chain-of-thought chunk (shown in the frontend bubbles)."""
        await self._send({"type": "cot_chunk", "payload": {"chunk": chunk}})

    async def send_p2p(
        self, to: str, msg_type: str, content: dict[str, Any], reasoning: str | None = None
    ) -> None:
        await self._send(
            {
                "type": "p2p_message",
                "payload": {"to": to, "msg_type": msg_type, "content": content, "reasoning": reasoning},
            }
        )

    async def send_mission_complete(self, result: dict[str, Any]) -> None:
        await self._send({"type": "mission_complete", "payload": {"result": result}})

    async def _send(self, message: dict[str, Any]) -> None:
        if self._ws is None:
            raise RuntimeError("client not connected")
        await self._ws.send(json.dumps(message))

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
