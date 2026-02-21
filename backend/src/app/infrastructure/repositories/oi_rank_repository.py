from __future__ import annotations

from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.oi_rank.interfaces import OiRankCacheRepository, OiRankConfigRepository
from app.domain.oi_rank.models import OiRankCache, OiRankConfig, OiRankEntry
from app.infrastructure.db.models.oi_rank import OiRankCacheModel, OiRankConfigModel


class SqlOiRankConfigRepository(OiRankConfigRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get_config(self) -> Optional[OiRankConfig]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(OiRankConfigModel).order_by(OiRankConfigModel.id.desc()).limit(1)
            )
            model = result.scalars().first()
            if model is None:
                return None
            return self._to_config(model)

    async def upsert(self, config: OiRankConfig) -> OiRankConfig:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(OiRankConfigModel).order_by(OiRankConfigModel.id.desc()).limit(1)
            )
            model = result.scalars().first()
            if model is None:
                model = OiRankConfigModel()
                session.add(model)

            model.refresh_interval_minutes = config.refresh_interval_minutes
            model.stale_ttl_minutes = config.stale_ttl_minutes

            await session.commit()
            await session.refresh(model)
            return self._to_config(model)

    def _to_config(self, model: OiRankConfigModel) -> OiRankConfig:
        return OiRankConfig(
            refresh_interval_minutes=model.refresh_interval_minutes,
            stale_ttl_minutes=model.stale_ttl_minutes,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class SqlOiRankCacheRepository(OiRankCacheRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get_cache(self, interval: str, metric: str, direction: str) -> Optional[OiRankCache]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(OiRankCacheModel).where(
                    OiRankCacheModel.interval == interval,
                    OiRankCacheModel.metric == metric,
                    OiRankCacheModel.direction == direction,
                )
            )
            model = result.scalars().first()
            if model is None:
                return None
            return self._to_cache(model)

    async def list_by_interval(self, interval: str) -> List[OiRankCache]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(OiRankCacheModel).where(OiRankCacheModel.interval == interval)
            )
            models = result.scalars().all()
            return [self._to_cache(model) for model in models]

    async def upsert(self, cache: OiRankCache) -> OiRankCache:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(OiRankCacheModel).where(
                    OiRankCacheModel.interval == cache.interval,
                    OiRankCacheModel.metric == cache.metric,
                    OiRankCacheModel.direction == cache.direction,
                )
            )
            model = result.scalars().first()
            if model is None:
                model = OiRankCacheModel(
                    interval=cache.interval,
                    metric=cache.metric,
                    direction=cache.direction,
                )
                session.add(model)

            model.limit = cache.limit
            model.payload = _entries_to_payload(cache.entries)
            model.status = cache.status
            model.data_updated_at = cache.data_updated_at
            model.refresh_started_at = cache.refresh_started_at
            model.last_error = cache.last_error

            await session.commit()
            await session.refresh(model)
            return self._to_cache(model)

    def _to_cache(self, model: OiRankCacheModel) -> OiRankCache:
        return OiRankCache(
            interval=model.interval,
            metric=model.metric,
            direction=model.direction,
            limit=model.limit,
            entries=_payload_to_entries(model.payload or []),
            status=model.status,
            data_updated_at=model.data_updated_at,
            refresh_started_at=model.refresh_started_at,
            last_error=model.last_error,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


def _payload_to_entries(payload: list) -> List[OiRankEntry]:
    entries: List[OiRankEntry] = []
    for item in payload or []:
        if not isinstance(item, dict):
            continue
        symbol = item.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            continue
        try:
            rank = int(item.get("rank", len(entries) + 1))
        except (TypeError, ValueError):
            rank = len(entries) + 1
        delta = item.get("delta")
        try:
            delta_val = float(delta)
        except (TypeError, ValueError):
            continue
        delta_pct = _safe_float(item.get("delta_pct"))
        current = _safe_float(item.get("current"))
        previous = _safe_float(item.get("previous"))
        entries.append(
            OiRankEntry(
                symbol=str(symbol),
                rank=rank,
                delta=delta_val,
                delta_pct=delta_pct,
                current=current,
                previous=previous,
            )
        )
    return entries


def _entries_to_payload(entries: List[OiRankEntry]) -> list:
    payload: list[dict] = []
    for entry in entries:
        payload.append(
            {
                "symbol": entry.symbol,
                "rank": entry.rank,
                "delta": entry.delta,
                "delta_pct": entry.delta_pct,
                "current": entry.current,
                "previous": entry.previous,
            }
        )
    return payload


def _safe_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

