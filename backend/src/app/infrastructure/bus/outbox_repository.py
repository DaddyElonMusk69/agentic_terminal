from datetime import datetime, timezone
from typing import Iterable, List, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.bus.models import OutboxMessage
from app.infrastructure.db.models.outbox import OutboxMessageModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OutboxRepository:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def enqueue(self, message: OutboxMessage) -> None:
        async with self._sessionmaker() as session:
            model = OutboxMessageModel(
                id=message.id,
                message_type=message.message_type,
                topic=message.topic,
                payload=message.payload,
                status=message.status,
                error=message.error,
                created_at=message.created_at,
                processed_at=message.processed_at,
            )
            session.add(model)
            await session.commit()

    async def get_pending(self, limit: int = 100) -> List[OutboxMessage]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(OutboxMessageModel)
                .where(OutboxMessageModel.status == "pending")
                .order_by(OutboxMessageModel.created_at)
                .limit(limit)
            )
            return [self._to_message(row) for row in result.scalars().all()]

    async def mark_processed(self, message_id: str) -> None:
        async with self._sessionmaker() as session:
            await session.execute(
                update(OutboxMessageModel)
                .where(OutboxMessageModel.id == message_id)
                .values(status="processed", processed_at=_utcnow(), error=None)
            )
            await session.commit()

    async def mark_failed(self, message_id: str, error: str) -> None:
        async with self._sessionmaker() as session:
            await session.execute(
                update(OutboxMessageModel)
                .where(OutboxMessageModel.id == message_id)
                .values(status="failed", processed_at=_utcnow(), error=error)
            )
            await session.commit()

    async def delete_by_session_id(self, session_id: str) -> int:
        async with self._sessionmaker() as session:
            result = await session.execute(
                delete(OutboxMessageModel).where(
                    OutboxMessageModel.payload["session_id"].as_string() == session_id
                )
            )
            await session.commit()
            return int(result.rowcount or 0)

    async def delete_older_than(self, cutoff: datetime, statuses: Optional[Iterable[str]] = None) -> int:
        conditions = [OutboxMessageModel.created_at < cutoff]
        if statuses:
            conditions.append(OutboxMessageModel.status.in_(list(statuses)))
        async with self._sessionmaker() as session:
            result = await session.execute(delete(OutboxMessageModel).where(*conditions))
            await session.commit()
            return int(result.rowcount or 0)

    def _to_message(self, model: OutboxMessageModel) -> OutboxMessage:
        return OutboxMessage(
            id=model.id,
            message_type=model.message_type,
            topic=model.topic,
            payload=model.payload,
            created_at=model.created_at,
            status=model.status,
            error=model.error,
            processed_at=model.processed_at,
        )
