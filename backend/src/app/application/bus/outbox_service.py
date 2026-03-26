from datetime import datetime, timezone
import logging
import math
from typing import Any, Awaitable, Callable, Dict, Optional
from uuid import uuid4

from app.application.bus.models import OutboxMessage
from app.infrastructure.bus.outbox_repository import OutboxRepository


HistoryRecorder = Callable[[str, Dict[str, Any]], Awaitable[None]]


logger = logging.getLogger(__name__)


class OutboxService:
    def __init__(
        self,
        repository: OutboxRepository,
        history_recorder: Optional[HistoryRecorder] = None,
    ) -> None:
        self._repository = repository
        self._history_recorder = history_recorder

    async def enqueue_event(self, topic: str, payload: Dict[str, Any]) -> OutboxMessage:
        return await self._enqueue("event", topic, payload)

    async def enqueue_command(self, topic: str, payload: Dict[str, Any]) -> OutboxMessage:
        return await self._enqueue("command", topic, payload)

    async def _enqueue(self, message_type: str, topic: str, payload: Dict[str, Any]) -> OutboxMessage:
        safe_payload = _serialize_payload(payload)
        message = OutboxMessage(
            id=str(uuid4()),
            message_type=message_type,  # type: ignore[arg-type]
            topic=topic,
            payload=safe_payload,
            created_at=datetime.now(timezone.utc),
        )
        await self._repository.enqueue(message)
        if self._history_recorder is not None:
            try:
                await self._history_recorder(topic, safe_payload)
            except Exception as exc:  # pragma: no cover - best-effort history
                logger.warning("History recorder failed for %s: %s", topic, exc)
        return message


def _serialize_payload(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: _serialize_payload(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_serialize_payload(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_serialize_payload(item) for item in value)
    return value
