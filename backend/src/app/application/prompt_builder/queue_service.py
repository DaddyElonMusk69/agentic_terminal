from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Any
from uuid import uuid4

from app.application.prompt_builder.queue_worker import PromptQueuePolicy
from app.infrastructure.repositories.prompt_build_queue_repository import PromptBuildQueueRepository


class PromptBuildQueueService:
    def __init__(
        self,
        repository: PromptBuildQueueRepository,
        policy: PromptQueuePolicy | None = None,
    ) -> None:
        self._repository = repository
        self._policy = policy or PromptQueuePolicy()

    async def enqueue(self, payload: Dict[str, Any]) -> str:
        request_id = str(payload.get("request_id") or uuid4())
        payload = dict(payload)
        payload["request_id"] = request_id

        expires_at = datetime.now(timezone.utc) + timedelta(minutes=self._policy.ttl_minutes)
        await self._repository.enqueue(request_id, payload, expires_at)
        return request_id
