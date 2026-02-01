from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import case, delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.ema_scanner.interfaces import EmaScannerConfigRepository
from app.domain.ema_scanner.models import EmaScannerLine
from app.infrastructure.db.models.ema_scanner import (
    EmaScannerConfigModel,
    EmaScannerLineModel,
    MonitoredAssetModel,
    MonitoredCoinModel,
    MonitoredIntervalModel,
)


class SqlEmaScannerRepository(EmaScannerConfigRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get_tolerance(self) -> Optional[float]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(EmaScannerConfigModel).order_by(EmaScannerConfigModel.id)
            )
            model = result.scalars().first()
            return model.tolerance_pct if model else None

    async def set_tolerance(self, value: float) -> float:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(EmaScannerConfigModel).order_by(EmaScannerConfigModel.id)
            )
            model = result.scalars().first()
            if model:
                model.tolerance_pct = value
                model.updated_at = datetime.now(timezone.utc)
            else:
                model = EmaScannerConfigModel(
                    tolerance_pct=value,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                session.add(model)
            await session.commit()
            return model.tolerance_pct

    async def list_ema_lines(self) -> List[int]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(EmaScannerLineModel.length).order_by(EmaScannerLineModel.length)
            )
            return [row[0] for row in result.fetchall()]

    async def list_ema_line_records(self) -> List[EmaScannerLine]:
        async with self._sessionmaker() as session:
            return await _fetch_line_records(session)

    async def add_ema_line(self, length: int) -> List[EmaScannerLine]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(EmaScannerLineModel.id).where(EmaScannerLineModel.length == length)
            )
            if result.scalar() is None:
                session.add(
                    EmaScannerLineModel(
                        length=length,
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await session.commit()
            return await _fetch_line_records(session)

    async def remove_ema_line(self, line_id: int) -> List[EmaScannerLine]:
        async with self._sessionmaker() as session:
            await session.execute(
                delete(EmaScannerLineModel).where(EmaScannerLineModel.id == line_id)
            )
            await session.commit()
            return await _fetch_line_records(session)

    async def list_monitored_coins(self) -> List[str]:
        async with self._sessionmaker() as session:
            order_nulls_last = case(
                (MonitoredCoinModel.display_order.is_(None), 1),
                else_=0,
            )
            result = await session.execute(
                select(MonitoredCoinModel.symbol).order_by(
                    order_nulls_last,
                    MonitoredCoinModel.display_order,
                    MonitoredCoinModel.symbol,
                )
            )
            return [row[0] for row in result.fetchall()]

    async def list_monitored_assets(self) -> List[str]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(MonitoredAssetModel.symbol).order_by(MonitoredAssetModel.symbol)
            )
            return [row[0] for row in result.fetchall()]

    async def list_monitored_intervals(self) -> List[str]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(MonitoredIntervalModel.interval).order_by(
                    MonitoredIntervalModel.display_order,
                    MonitoredIntervalModel.interval,
                )
            )
            return [row[0] for row in result.fetchall()]


async def _fetch_line_records(session: AsyncSession) -> List[EmaScannerLine]:
    result = await session.execute(
        select(EmaScannerLineModel).order_by(EmaScannerLineModel.length)
    )
    return [
        EmaScannerLine(id=model.id, length=model.length)
        for model in result.scalars().all()
    ]
