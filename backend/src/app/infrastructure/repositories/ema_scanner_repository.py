import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import case, delete, insert, select, text, update
from sqlalchemy.exc import ProgrammingError
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

logger = logging.getLogger(__name__)


class SqlEmaScannerRepository(EmaScannerConfigRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker
        self._scan_intervals_supported: bool | None = None
        self._scan_intervals_missing_logged = False

    async def get_tolerance(self) -> Optional[float]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(EmaScannerConfigModel.tolerance_pct).order_by(EmaScannerConfigModel.id)
            )
            return result.scalars().first()

    async def set_tolerance(self, value: float) -> float:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(EmaScannerConfigModel.id).order_by(EmaScannerConfigModel.id)
            )
            config_id = result.scalars().first()
            now = datetime.now(timezone.utc)
            if config_id is not None:
                await session.execute(
                    update(EmaScannerConfigModel)
                    .where(EmaScannerConfigModel.id == config_id)
                    .values(tolerance_pct=value, updated_at=now)
                )
            else:
                await session.execute(
                    insert(EmaScannerConfigModel).values(
                        tolerance_pct=value,
                        created_at=now,
                        updated_at=now,
                    )
                )
            await session.commit()
            return value

    async def get_scan_intervals(self) -> List[str] | None:
        async with self._sessionmaker() as session:
            if not await self._supports_scan_intervals(session):
                return None
            try:
                result = await session.execute(
                    select(EmaScannerConfigModel.scan_intervals).order_by(EmaScannerConfigModel.id)
                )
            except ProgrammingError as exc:
                if self._is_missing_scan_intervals_error(exc):
                    await session.rollback()
                    self._mark_scan_intervals_missing()
                    return None
                raise
            raw = result.scalars().first()
            if not isinstance(raw, list):
                return None
            return [
                str(item).strip()
                for item in raw
                if isinstance(item, str) and str(item).strip()
            ]

    async def set_scan_intervals(self, intervals: List[str] | None) -> List[str] | None:
        normalized = None
        if isinstance(intervals, list):
            normalized = []
            seen: set[str] = set()
            for item in intervals:
                if not isinstance(item, str):
                    continue
                value = item.strip()
                if not value or value in seen:
                    continue
                seen.add(value)
                normalized.append(value)
        async with self._sessionmaker() as session:
            if not await self._supports_scan_intervals(session):
                return None
            result = await session.execute(
                select(EmaScannerConfigModel.id).order_by(EmaScannerConfigModel.id)
            )
            config_id = result.scalars().first()
            now = datetime.now(timezone.utc)
            try:
                if config_id is not None:
                    await session.execute(
                        update(EmaScannerConfigModel)
                        .where(EmaScannerConfigModel.id == config_id)
                        .values(scan_intervals=normalized, updated_at=now)
                    )
                else:
                    await session.execute(
                        insert(EmaScannerConfigModel).values(
                            tolerance_pct=0.2,
                            scan_intervals=normalized,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                await session.commit()
                return normalized
            except ProgrammingError as exc:
                if self._is_missing_scan_intervals_error(exc):
                    await session.rollback()
                    self._mark_scan_intervals_missing()
                    return None
                raise

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

    async def _supports_scan_intervals(self, session: AsyncSession) -> bool:
        if self._scan_intervals_supported is True:
            return self._scan_intervals_supported
        dialect_name = session.bind.dialect.name if session.bind is not None else ""
        if dialect_name == "postgresql":
            result = await session.execute(
                text(
                    """
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'ema_scanner_config'
                      AND column_name = 'scan_intervals'
                    LIMIT 1
                    """
                )
            )
            supported = result.scalar() is not None
        elif dialect_name == "sqlite":
            result = await session.execute(text("PRAGMA table_info('ema_scanner_config')"))
            supported = any(
                len(row) > 1 and str(row[1]) == "scan_intervals"
                for row in result.fetchall()
            )
        else:
            supported = True
        if supported:
            self._scan_intervals_supported = True
            self._scan_intervals_missing_logged = False
            return True
        self._mark_scan_intervals_missing()
        return False

    def _mark_scan_intervals_missing(self) -> None:
        self._scan_intervals_supported = False
        if self._scan_intervals_missing_logged:
            return
        logger.warning(
            "EMA scanner scan_intervals column missing; using global monitored intervals until migration is applied."
        )
        self._scan_intervals_missing_logged = True

    @staticmethod
    def _is_missing_scan_intervals_error(exc: ProgrammingError) -> bool:
        message = str(exc).lower()
        return "scan_intervals" in message and "does not exist" in message


async def _fetch_line_records(session: AsyncSession) -> List[EmaScannerLine]:
    result = await session.execute(
        select(EmaScannerLineModel).order_by(EmaScannerLineModel.length)
    )
    return [
        EmaScannerLine(id=model.id, length=model.length)
        for model in result.scalars().all()
    ]
