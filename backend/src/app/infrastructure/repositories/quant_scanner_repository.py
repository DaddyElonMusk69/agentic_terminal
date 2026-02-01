from typing import List

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.quant_scanner.interfaces import QuantScannerConfigRepository
from app.infrastructure.db.models.ema_scanner import (
    MonitoredAssetModel,
    MonitoredCoinModel,
    MonitoredIntervalModel,
)


class SqlQuantScannerRepository(QuantScannerConfigRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def list_monitored_coins(self) -> List[str]:
        async with self._sessionmaker() as session:
            order_nulls_last = case(
                (MonitoredCoinModel.display_order.is_(None), 1),
                else_=0,
            )
            result = await session.execute(
                select(MonitoredCoinModel.symbol)
                .order_by(order_nulls_last, MonitoredCoinModel.display_order, MonitoredCoinModel.symbol)
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
                select(MonitoredIntervalModel.interval)
                .order_by(MonitoredIntervalModel.display_order, MonitoredIntervalModel.interval)
            )
            return [row[0] for row in result.fetchall()]
