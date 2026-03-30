from typing import List

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.market_settings.interfaces import MarketSettingsRepository
from app.infrastructure.db.models.ema_scanner import MonitoredAssetModel, MonitoredIntervalModel


# Keep the second manual source in the existing asset table to avoid a schema fork.
US_STOCK_ASSET_PREFIX = "__US_STOCK__:"


class SqlMarketSettingsRepository(MarketSettingsRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def list_assets(self) -> List[str]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(MonitoredAssetModel.symbol).order_by(MonitoredAssetModel.symbol)
            )
            return [
                row[0]
                for row in result.fetchall()
                if isinstance(row[0], str) and not row[0].startswith(US_STOCK_ASSET_PREFIX)
            ]

    async def list_us_stock_assets(self) -> List[str]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(MonitoredAssetModel.symbol).order_by(MonitoredAssetModel.symbol)
            )
            return [
                row[0][len(US_STOCK_ASSET_PREFIX) :]
                for row in result.fetchall()
                if isinstance(row[0], str) and row[0].startswith(US_STOCK_ASSET_PREFIX)
            ]

    async def list_intervals(self) -> List[str]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(MonitoredIntervalModel.interval).order_by(
                    MonitoredIntervalModel.display_order,
                    MonitoredIntervalModel.interval,
                )
            )
            return [row[0] for row in result.fetchall()]

    async def add_asset(self, symbol: str) -> None:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(MonitoredAssetModel.id).where(MonitoredAssetModel.symbol == symbol)
            )
            if result.scalar() is None:
                session.add(MonitoredAssetModel(symbol=symbol))
                await session.commit()

    async def add_us_stock_asset(self, symbol: str) -> None:
        prefixed_symbol = f"{US_STOCK_ASSET_PREFIX}{symbol}"
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(MonitoredAssetModel.id).where(MonitoredAssetModel.symbol == prefixed_symbol)
            )
            if result.scalar() is None:
                session.add(MonitoredAssetModel(symbol=prefixed_symbol))
                await session.commit()

    async def remove_asset(self, symbol: str) -> None:
        async with self._sessionmaker() as session:
            await session.execute(
                delete(MonitoredAssetModel).where(MonitoredAssetModel.symbol == symbol)
            )
            await session.commit()

    async def remove_us_stock_asset(self, symbol: str) -> None:
        prefixed_symbol = f"{US_STOCK_ASSET_PREFIX}{symbol}"
        async with self._sessionmaker() as session:
            await session.execute(
                delete(MonitoredAssetModel).where(MonitoredAssetModel.symbol == prefixed_symbol)
            )
            await session.commit()

    async def add_interval(self, interval: str) -> None:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(MonitoredIntervalModel.id).where(MonitoredIntervalModel.interval == interval)
            )
            if result.scalar() is not None:
                return
            max_order_result = await session.execute(
                select(func.max(MonitoredIntervalModel.display_order))
            )
            max_order = max_order_result.scalar() or 0
            session.add(
                MonitoredIntervalModel(
                    interval=interval,
                    display_order=int(max_order) + 1,
                )
            )
            await session.commit()

    async def remove_interval(self, interval: str) -> None:
        async with self._sessionmaker() as session:
            await session.execute(
                delete(MonitoredIntervalModel).where(MonitoredIntervalModel.interval == interval)
            )
            await session.commit()
