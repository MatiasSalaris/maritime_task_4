from __future__ import annotations
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel


class MessageType(str, Enum):
    INTENT = "intent"           # lead asset re-expresses the human's order for the team
    PROPOSAL = "proposal"
    ACK = "ack"
    OBJECTION = "objection"
    HANDOFF = "handoff"
    STATUS = "status"
    REPORT = "report"


class P2PMessage(BaseModel):
    id: str
    from_agent: str
    to_agent: str               # agent_id or "all"
    msg_type: MessageType
    content: dict[str, Any]
    reasoning: Optional[str] = None
    sent_at: float
