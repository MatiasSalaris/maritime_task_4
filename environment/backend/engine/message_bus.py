from __future__ import annotations
from collections import defaultdict
from models.messages import P2PMessage


class MessageBus:
    def __init__(self) -> None:
        self._inbox: dict[str, list[P2PMessage]] = defaultdict(list)
        self._log: list[P2PMessage] = []
        self._in_flight: list[P2PMessage] = []   # recent, for frontend animation

    def route(self, message: P2PMessage, all_agent_ids: list[str]) -> None:
        self._log.append(message)
        self._in_flight.append(message)

        if message.to_agent == "all":
            for agent_id in all_agent_ids:
                if agent_id != message.from_agent:
                    self._inbox[agent_id].append(message)
        else:
            self._inbox[message.to_agent].append(message)

    def drain_inbox(self, agent_id: str) -> list[P2PMessage]:
        msgs = list(self._inbox[agent_id])
        self._inbox[agent_id].clear()
        return msgs

    def expire_in_flight(self, max_age_s: float, now: float) -> None:
        self._in_flight = [m for m in self._in_flight if (now - m.sent_at) < max_age_s]

    def in_flight_dicts(self) -> list[dict]:
        return [m.model_dump() for m in self._in_flight]

    def log_dicts(self, n: int = 100) -> list[dict]:
        return [m.model_dump() for m in self._log[-n:]]


# Module-level singleton
message_bus = MessageBus()
