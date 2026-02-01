from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from uuid import uuid4

from app.infrastructure.repositories.order_queue_repository import OrderQueueRepository


class OrderQueuePolicy:
    def __init__(self, ttl_minutes: int = 5) -> None:
        self.ttl_minutes = ttl_minutes


class OrderQueueService:
    def __init__(self, repository: OrderQueueRepository, policy: OrderQueuePolicy | None = None) -> None:
        self._repository = repository
        self._policy = policy or OrderQueuePolicy()

    async def enqueue(self, payload: Dict[str, Any]) -> str:
        request_id = str(payload.get("request_id") or uuid4())
        payload = dict(payload)
        payload["request_id"] = request_id

        expires_at = datetime.now(timezone.utc) + timedelta(minutes=self._policy.ttl_minutes)
        await self._repository.enqueue(request_id, payload, expires_at)
        return request_id
