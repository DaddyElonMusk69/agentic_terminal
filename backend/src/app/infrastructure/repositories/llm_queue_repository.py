from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.db.models.llm_queue import LlmQueueRequestModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class LlmQueueItem:
    id: str
    payload: dict
    status: str
    created_at: datetime
    expires_at: Optional[datetime]


class LlmQueueRepository:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def enqueue(self, request_id: str, payload: dict, expires_at: Optional[datetime]) -> None:
        async with self._sessionmaker() as session:
            model = LlmQueueRequestModel(
                id=request_id,
                status="queued",
                payload=payload,
                created_at=_utcnow(),
                updated_at=_utcnow(),
                expires_at=expires_at,
            )
            session.add(model)
            await session.commit()

    async def claim_next(self) -> Optional[LlmQueueItem]:
        async with self._sessionmaker() as session:
            async with session.begin():
                result = await session.execute(
                    select(LlmQueueRequestModel)
                    .where(LlmQueueRequestModel.status == "queued")
                    .order_by(LlmQueueRequestModel.created_at)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                model = result.scalars().first()
                if model is None:
                    return None
                now = _utcnow()
                model.status = "in_progress"
                model.started_at = now
                model.updated_at = now

            return LlmQueueItem(
                id=model.id,
                payload=model.payload,
                status=model.status,
                created_at=model.created_at,
                expires_at=model.expires_at,
            )

    async def mark_done(self, request_id: str, result: dict) -> None:
        await self._finalize(request_id, "done", result=result, error=None)

    async def mark_failed(self, request_id: str, error: str) -> None:
        await self._finalize(request_id, "failed", result=None, error=error)

    async def mark_dropped(self, request_id: str, reason: str) -> None:
        await self._finalize(request_id, "dropped", result=None, error=reason)

    async def _finalize(
        self,
        request_id: str,
        status: str,
        result: Optional[dict],
        error: Optional[str],
    ) -> None:
        async with self._sessionmaker() as session:
            await session.execute(
                update(LlmQueueRequestModel)
                .where(LlmQueueRequestModel.id == request_id)
                .values(
                    status=status,
                    result=result,
                    error=error,
                    completed_at=_utcnow(),
                    updated_at=_utcnow(),
                )
            )
            await session.commit()
