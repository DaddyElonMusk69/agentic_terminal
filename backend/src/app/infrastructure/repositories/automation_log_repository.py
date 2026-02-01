from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.automation_history.interfaces import AutomationLogRepository
from app.domain.automation_history.models import AutomationLogRecord
from app.infrastructure.db.models.automation import AutomationLogModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SqlAutomationLogRepository(AutomationLogRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def create_log(
        self,
        session_id: str,
        log_type: str,
        data: Optional[dict],
        cycle_number: int = 0,
    ) -> AutomationLogRecord:
        async with self._sessionmaker() as session:
            record = AutomationLogModel(
                session_id=session_id,
                log_type=log_type,
                cycle_number=int(cycle_number),
                data=data or {},
                created_at=_utcnow(),
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return _to_record(record)

    async def list_by_session(
        self,
        session_id: str,
        limit: int,
        offset: int,
    ) -> List[AutomationLogRecord]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(AutomationLogModel)
                .where(AutomationLogModel.session_id == session_id)
                .order_by(AutomationLogModel.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            return [_to_record(model) for model in result.scalars().all()]

    async def delete_by_session(self, session_id: str) -> int:
        async with self._sessionmaker() as session:
            result = await session.execute(
                delete(AutomationLogModel).where(AutomationLogModel.session_id == session_id)
            )
            await session.commit()
            return int(result.rowcount or 0)


def _to_record(model: AutomationLogModel) -> AutomationLogRecord:
    return AutomationLogRecord(
        id=model.id,
        session_id=model.session_id,
        created_at=model.created_at,
        log_type=model.log_type,
        cycle_number=model.cycle_number,
        data=model.data,
    )
