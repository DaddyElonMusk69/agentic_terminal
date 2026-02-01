from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.application.prompt_builder.service import PromptBuilderService, PromptBuildError
from app.domain.prompt_builder.models import PromptBuildRequest
from app.infrastructure.repositories.prompt_build_queue_repository import (
    PromptBuildQueueRepository,
    PromptBuildQueueItem,
)


@dataclass(frozen=True)
class PromptQueuePolicy:
    ttl_minutes: int = 20


class PromptBuildQueueWorker:
    def __init__(
        self,
        repository: PromptBuildQueueRepository,
        prompt_builder: PromptBuilderService,
        policy: Optional[PromptQueuePolicy] = None,
    ) -> None:
        self._repository = repository
        self._prompt_builder = prompt_builder
        self._policy = policy or PromptQueuePolicy()

    async def process_next(self) -> bool:
        item = await self._repository.claim_next()
        if item is None:
            return False

        if _is_expired(item, self._policy):
            await self._repository.mark_dropped(item.id, "expired")
            return True

        try:
            request = PromptBuildRequest.from_payload(item.payload)
            result = await self._prompt_builder.build(request)
            await self._repository.mark_done(item.id, result.to_dict())
        except PromptBuildError as exc:
            await self._repository.mark_failed(item.id, str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            await self._repository.mark_failed(item.id, f"unexpected_error: {exc}")

        return True


def _is_expired(item: PromptBuildQueueItem, policy: PromptQueuePolicy) -> bool:
    now = datetime.now(timezone.utc)
    expires_at = item.expires_at
    if expires_at is None:
        expires_at = item.created_at + timedelta(minutes=policy.ttl_minutes)
    return now > expires_at
