from typing import Iterable, List, Set

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.db.models.ema_scanner import MonitoredAssetPositionModel


class MonitoredAssetPositionRepository:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def list_assets(self) -> List[str]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(MonitoredAssetPositionModel.symbol).order_by(
                    MonitoredAssetPositionModel.symbol
                )
            )
            return [row[0] for row in result.fetchall()]

    async def add_assets(self, symbols: Iterable[str]) -> None:
        normalized = {symbol for symbol in symbols if symbol}
        if not normalized:
            return
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(MonitoredAssetPositionModel.symbol).where(
                    MonitoredAssetPositionModel.symbol.in_(normalized)
                )
            )
            existing: Set[str] = {row[0] for row in result.fetchall()}
            for symbol in sorted(normalized):
                if symbol in existing:
                    continue
                session.add(MonitoredAssetPositionModel(symbol=symbol))
            await session.commit()

    async def sync_assets(self, symbols: Iterable[str]) -> None:
        normalized = {symbol for symbol in symbols if symbol}
        async with self._sessionmaker() as session:
            if normalized:
                await session.execute(
                    delete(MonitoredAssetPositionModel).where(
                        ~MonitoredAssetPositionModel.symbol.in_(normalized)
                    )
                )
                result = await session.execute(
                    select(MonitoredAssetPositionModel.symbol).where(
                        MonitoredAssetPositionModel.symbol.in_(normalized)
                    )
                )
                existing: Set[str] = {row[0] for row in result.fetchall()}
                for symbol in sorted(normalized):
                    if symbol in existing:
                        continue
                    session.add(MonitoredAssetPositionModel(symbol=symbol))
            else:
                await session.execute(delete(MonitoredAssetPositionModel))
            await session.commit()
