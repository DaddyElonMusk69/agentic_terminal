from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Literal

MessageType = Literal["command", "event"]


@dataclass(frozen=True)
class OutboxMessage:
    id: str
    message_type: MessageType
    topic: str
    payload: Dict[str, Any]
    created_at: datetime
    status: str = "pending"
    error: str | None = None
    processed_at: datetime | None = None
