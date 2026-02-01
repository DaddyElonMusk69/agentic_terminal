from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.automation_history.interfaces import AutomationTradeRepository
from app.domain.automation_history.models import AutomationTradeRecord
from app.infrastructure.db.models.automation import AutomationTradeModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SqlAutomationTradeRepository(AutomationTradeRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def create_trade(
        self,
        session_id: str,
        symbol: str,
        direction: Optional[str],
        action: Optional[str],
        entry_price: Optional[float],
        exit_price: Optional[float],
        size_usd: Optional[float],
        pnl: Optional[float],
        pnl_pct: Optional[float],
        status: Optional[str],
        closed_at,
        signal_data: Optional[dict],
        llm_reasoning: Optional[str],
        llm_response_full: Optional[str],
        order_id: Optional[str],
        fill_price: Optional[float],
        cycle_number: int = 0,
    ) -> AutomationTradeRecord:
        async with self._sessionmaker() as session:
            record = AutomationTradeModel(
                session_id=session_id,
                symbol=symbol,
                direction=direction,
                action=action,
                entry_price=entry_price,
                exit_price=exit_price,
                size_usd=size_usd,
                pnl=pnl,
                pnl_pct=pnl_pct,
                status=status or "open",
                closed_at=closed_at,
                signal_data=signal_data,
                llm_reasoning=llm_reasoning,
                llm_response_full=llm_response_full,
                order_id=order_id,
                fill_price=fill_price,
                cycle_number=int(cycle_number),
                created_at=_utcnow(),
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return _to_record(record)

    async def list_by_session(self, session_id: str) -> List[AutomationTradeRecord]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(AutomationTradeModel)
                .where(AutomationTradeModel.session_id == session_id)
                .order_by(AutomationTradeModel.created_at.desc())
            )
            return [_to_record(model) for model in result.scalars().all()]

    async def count_by_session(self, session_id: str) -> int:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(func.count(AutomationTradeModel.id)).where(
                    AutomationTradeModel.session_id == session_id,
                    AutomationTradeModel.status != "failed",
                )
            )
            return int(result.scalar_one() or 0)

    async def sum_pnl_by_session(self, session_id: str) -> float:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(func.coalesce(func.sum(AutomationTradeModel.pnl), 0.0)).where(
                    AutomationTradeModel.session_id == session_id
                )
            )
            value = result.scalar_one()
            try:
                return float(value or 0.0)
            except (TypeError, ValueError):
                return 0.0

    async def delete_by_session(self, session_id: str) -> int:
        async with self._sessionmaker() as session:
            result = await session.execute(
                delete(AutomationTradeModel).where(AutomationTradeModel.session_id == session_id)
            )
            await session.commit()
            return int(result.rowcount or 0)


def _to_record(model: AutomationTradeModel) -> AutomationTradeRecord:
    return AutomationTradeRecord(
        id=model.id,
        session_id=model.session_id,
        created_at=model.created_at,
        cycle_number=model.cycle_number,
        symbol=model.symbol,
        direction=model.direction,
        action=model.action,
        entry_price=model.entry_price,
        exit_price=model.exit_price,
        size_usd=model.size_usd,
        pnl=model.pnl,
        pnl_pct=model.pnl_pct,
        status=model.status,
        closed_at=model.closed_at,
        signal_data=model.signal_data,
        llm_reasoning=model.llm_reasoning,
        llm_response_full=model.llm_response_full,
        order_id=model.order_id,
        fill_price=model.fill_price,
    )
