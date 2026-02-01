from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.automation_history.interfaces import AutomationSessionRepository
from app.domain.automation_history.models import AutomationSessionRecord
from app.infrastructure.db.models.automation import AutomationSessionModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SqlAutomationSessionRepository(AutomationSessionRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def create_session(
        self,
        session_id: str,
        execution_mode: str,
        provider: Optional[str],
        model: Optional[str],
        config_snapshot: Optional[dict],
    ) -> AutomationSessionRecord:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(AutomationSessionModel).where(AutomationSessionModel.id == session_id)
            )
            record = result.scalars().first()
            if record is None:
                record = AutomationSessionModel(
                    id=session_id,
                    started_at=_utcnow(),
                )
                session.add(record)

            record.execution_mode = execution_mode
            record.provider = provider
            record.model = model
            record.config_snapshot = config_snapshot

            await session.commit()
            await session.refresh(record)
            return _to_record(record)

    async def get_by_id(self, session_id: str) -> Optional[AutomationSessionRecord]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(AutomationSessionModel).where(AutomationSessionModel.id == session_id)
            )
            record = result.scalars().first()
            return _to_record(record) if record else None

    async def list_all(self, limit: int, offset: int) -> List[AutomationSessionRecord]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(AutomationSessionModel)
                .order_by(AutomationSessionModel.started_at.desc())
                .offset(offset)
                .limit(limit)
            )
            return [_to_record(model) for model in result.scalars().all()]

    async def count_all(self) -> int:
        async with self._sessionmaker() as session:
            result = await session.execute(select(func.count(AutomationSessionModel.id)))
            return int(result.scalar_one() or 0)

    async def end_session(
        self,
        session_id: str,
        ended_at: datetime,
        total_cycles: int,
        total_trades: int,
        total_pnl: float,
    ) -> Optional[AutomationSessionRecord]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(AutomationSessionModel).where(AutomationSessionModel.id == session_id)
            )
            record = result.scalars().first()
            if record is None:
                return None

            record.ended_at = ended_at
            record.total_cycles = int(total_cycles)
            record.total_trades = int(total_trades)
            record.total_pnl = float(total_pnl)

            await session.commit()
            await session.refresh(record)
            return _to_record(record)

    async def increment_prompt_count(self, session_id: str, delta: int = 1) -> None:
        async with self._sessionmaker() as session:
            await session.execute(
                update(AutomationSessionModel)
                .where(AutomationSessionModel.id == session_id)
                .values(prompt_count=AutomationSessionModel.prompt_count + int(delta))
            )
            await session.commit()

    async def delete_session(self, session_id: str) -> bool:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(AutomationSessionModel).where(AutomationSessionModel.id == session_id)
            )
            record = result.scalars().first()
            if record is None:
                return False
            await session.delete(record)
            await session.commit()
            return True


def _to_record(model: AutomationSessionModel) -> AutomationSessionRecord:
    return AutomationSessionRecord(
        id=model.id,
        started_at=model.started_at,
        ended_at=model.ended_at,
        execution_mode=model.execution_mode,
        provider=model.provider,
        model=model.model,
        total_cycles=model.total_cycles,
        total_trades=model.total_trades,
        total_pnl=model.total_pnl,
        prompt_count=model.prompt_count,
        config_snapshot=model.config_snapshot,
    )
