from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional, Tuple

from app.domain.oi_rank.interfaces import OiRankCacheRepository, OiRankConfigRepository
from app.domain.oi_rank.models import OiRankCache, OiRankConfig, OiRankEntry
from app.infrastructure.external.binance_client import BinanceClient

logger = logging.getLogger(__name__)

SUPPORTED_INTERVALS = {"1h", "4h", "12h"}
SUPPORTED_METRICS = {"abs", "pct"}
SUPPORTED_DIRECTIONS = {"top", "low"}

DEFAULT_REFRESH_MINUTES = 30
MIN_REFRESH_MINUTES = 10
MAX_REFRESH_MINUTES = 720
DEFAULT_STALE_TTL_MINUTES = 90

DEFAULT_LIMIT = 5
MAX_CACHE_LIMIT = 100

SYMBOL_CACHE_TTL_SECONDS = 6 * 60 * 60


@dataclass(frozen=True)
class OiRankResult:
    interval: str
    metric: str
    direction: str
    status: str
    entries: Optional[List[OiRankEntry]]
    data_updated_at: Optional[datetime]
    refresh_started_at: Optional[datetime]
    last_error: Optional[str]


class OiRankService:
    def __init__(
        self,
        cache_repo: OiRankCacheRepository,
        config_repo: OiRankConfigRepository,
        binance_client: Optional[BinanceClient] = None,
    ) -> None:
        self._cache_repo = cache_repo
        self._config_repo = config_repo
        self._binance = binance_client or BinanceClient()
        self._refresh_tasks: Dict[str, asyncio.Task] = {}
        self._symbols_cache: Tuple[List[Tuple[str, str]], Optional[float]] = ([], None)

    async def get_config(self) -> OiRankConfig:
        config = await self._config_repo.get_config()
        if config is None:
            config = await self._config_repo.upsert(
                OiRankConfig(
                    refresh_interval_minutes=DEFAULT_REFRESH_MINUTES,
                    stale_ttl_minutes=DEFAULT_STALE_TTL_MINUTES,
                )
            )
        return self._normalize_config(config)

    async def update_config(self, refresh_interval_minutes: int, stale_ttl_minutes: int) -> OiRankConfig:
        refresh = int(refresh_interval_minutes)
        stale = int(stale_ttl_minutes)
        if refresh < MIN_REFRESH_MINUTES:
            raise ValueError("refresh_interval_minutes must be at least 10")
        if refresh > MAX_REFRESH_MINUTES:
            raise ValueError("refresh_interval_minutes must be 720 or less")
        if stale < refresh:
            stale = refresh
        config = OiRankConfig(
            refresh_interval_minutes=refresh,
            stale_ttl_minutes=stale,
        )
        return await self._config_repo.upsert(config)

    async def get_rank(
        self,
        direction: str,
        interval: str,
        limit: Optional[int] = None,
        metric: Optional[str] = None,
    ) -> OiRankResult:
        interval = _normalize_interval(interval)
        metric = _normalize_metric(metric)
        direction = _normalize_direction(direction)
        limit = _normalize_limit(limit)

        config = await self.get_config()
        now = _utcnow()
        cache = await self._cache_repo.get_cache(interval, metric, direction)

        entries = cache.entries if cache else []
        has_entries = bool(entries)
        updated_at = cache.data_updated_at if cache else None
        refresh_started_at = cache.refresh_started_at if cache else None
        last_error = cache.last_error if cache else None

        hard_stale = _is_hard_stale(updated_at, now, config.stale_ttl_minutes)
        soft_stale = _is_soft_stale(updated_at, now, config.refresh_interval_minutes, config.stale_ttl_minutes)

        if not has_entries:
            await self._maybe_trigger_refresh(interval, config)
            return OiRankResult(
                interval=interval,
                metric=metric,
                direction=direction,
                status="warming",
                entries=None,
                data_updated_at=updated_at,
                refresh_started_at=refresh_started_at,
                last_error=last_error,
            )

        if hard_stale:
            await self._maybe_trigger_refresh(interval, config)
            return OiRankResult(
                interval=interval,
                metric=metric,
                direction=direction,
                status="stale",
                entries=None,
                data_updated_at=updated_at,
                refresh_started_at=refresh_started_at,
                last_error=last_error,
            )

        if soft_stale:
            await self._maybe_trigger_refresh(interval, config)
            status = "warming"
        else:
            if cache and cache.status in {"warming", "error"}:
                status = cache.status
            else:
                status = "ready"

        return OiRankResult(
            interval=interval,
            metric=metric,
            direction=direction,
            status=status,
            entries=entries[:limit],
            data_updated_at=updated_at,
            refresh_started_at=refresh_started_at,
            last_error=last_error,
        )

    async def _maybe_trigger_refresh(self, interval: str, config: OiRankConfig) -> None:
        task = self._refresh_tasks.get(interval)
        if task and not task.done():
            return

        if await self._refresh_in_progress(interval, config):
            return

        started_at = _utcnow()
        await self._mark_warming(interval, started_at)
        task = asyncio.create_task(self._refresh_interval(interval, started_at))
        self._refresh_tasks[interval] = task

    async def _refresh_in_progress(self, interval: str, config: OiRankConfig) -> bool:
        caches = await self._cache_repo.list_by_interval(interval)
        lock_minutes = max(5, min(config.stale_ttl_minutes, config.refresh_interval_minutes * 2))
        now = _utcnow()
        for cache in caches:
            if cache.status != "warming" or cache.refresh_started_at is None:
                continue
            if (now - cache.refresh_started_at).total_seconds() / 60 <= lock_minutes:
                return True
        return False

    async def _mark_warming(self, interval: str, started_at: datetime) -> None:
        caches = await self._cache_repo.list_by_interval(interval)
        cache_map = {(cache.metric, cache.direction): cache for cache in caches}
        for metric in SUPPORTED_METRICS:
            for direction in SUPPORTED_DIRECTIONS:
                existing = cache_map.get((metric, direction))
                entries = existing.entries if existing else []
                data_updated_at = existing.data_updated_at if existing else None
                last_error = existing.last_error if existing else None
                limit = existing.limit if existing else MAX_CACHE_LIMIT
                cache = OiRankCache(
                    interval=interval,
                    metric=metric,
                    direction=direction,
                    limit=limit,
                    entries=entries,
                    status="warming",
                    data_updated_at=data_updated_at,
                    refresh_started_at=started_at,
                    last_error=last_error,
                )
                await self._cache_repo.upsert(cache)

    async def _refresh_interval(self, interval: str, started_at: datetime) -> None:
        try:
            symbols = await self._get_symbols()
            if not symbols:
                raise RuntimeError("no symbols available")

            entries = await self._fetch_entries(symbols, interval)
            if not entries:
                raise RuntimeError("no open interest data")

            now = _utcnow()
            await self._store_rankings(interval, entries, now, started_at)
        except Exception as exc:
            logger.warning("OI rank refresh failed for %s: %s", interval, exc)
            await self._mark_error(interval, str(exc), started_at)

    async def _store_rankings(
        self,
        interval: str,
        entries: List[dict],
        updated_at: datetime,
        started_at: datetime,
    ) -> None:
        abs_sorted = sorted(entries, key=lambda item: item["delta"], reverse=True)
        abs_low = list(reversed(abs_sorted))

        pct_entries = [item for item in entries if item.get("delta_pct") is not None]
        pct_sorted = sorted(pct_entries, key=lambda item: item["delta_pct"], reverse=True)
        pct_low = list(reversed(pct_sorted))

        payloads = {
            ("abs", "top"): _build_rank_entries(abs_sorted),
            ("abs", "low"): _build_rank_entries(abs_low),
            ("pct", "top"): _build_rank_entries(pct_sorted),
            ("pct", "low"): _build_rank_entries(pct_low),
        }

        for metric in SUPPORTED_METRICS:
            for direction in SUPPORTED_DIRECTIONS:
                ranked = payloads[(metric, direction)]
                cache = OiRankCache(
                    interval=interval,
                    metric=metric,
                    direction=direction,
                    limit=MAX_CACHE_LIMIT,
                    entries=ranked[:MAX_CACHE_LIMIT],
                    status="ready",
                    data_updated_at=updated_at,
                    refresh_started_at=started_at,
                    last_error=None,
                )
                await self._cache_repo.upsert(cache)

    async def _mark_error(self, interval: str, error: str, started_at: datetime) -> None:
        caches = await self._cache_repo.list_by_interval(interval)
        cache_map = {(cache.metric, cache.direction): cache for cache in caches}
        for metric in SUPPORTED_METRICS:
            for direction in SUPPORTED_DIRECTIONS:
                existing = cache_map.get((metric, direction))
                entries = existing.entries if existing else []
                cache = OiRankCache(
                    interval=interval,
                    metric=metric,
                    direction=direction,
                    limit=MAX_CACHE_LIMIT,
                    entries=entries,
                    status="error",
                    data_updated_at=existing.data_updated_at if existing else None,
                    refresh_started_at=started_at,
                    last_error=error,
                )
                await self._cache_repo.upsert(cache)

    async def _get_symbols(self) -> List[Tuple[str, str]]:
        cached, expires_at = self._symbols_cache
        now_ts = _utcnow().timestamp()
        if cached and expires_at and now_ts < expires_at:
            return cached

        symbols = await asyncio.to_thread(self._binance.fetch_usdt_perp_symbols)
        results: List[Tuple[str, str]] = []
        for symbol in symbols or []:
            if not isinstance(symbol, str) or not symbol:
                continue
            base = _strip_usdt(symbol)
            if base:
                results.append((base, symbol))
        if results:
            self._symbols_cache = (results, now_ts + SYMBOL_CACHE_TTL_SECONDS)
        return results

    async def _fetch_entries(self, symbols: List[Tuple[str, str]], interval: str) -> List[dict]:
        sem = asyncio.Semaphore(8)
        results: List[dict] = []

        async def fetch_one(base: str, full_symbol: str) -> None:
            async with sem:
                points = await asyncio.to_thread(
                    self._binance.fetch_open_interest_history,
                    full_symbol,
                    interval,
                    2,
                )
            if not points or len(points) < 2:
                return
            previous = points[-2].value
            current = points[-1].value
            if previous is None or current is None:
                return
            delta = current - previous
            delta_pct = None
            if previous:
                delta_pct = (delta / previous) * 100
            results.append(
                {
                    "symbol": base,
                    "delta": float(delta),
                    "delta_pct": float(delta_pct) if delta_pct is not None else None,
                    "current": float(current),
                    "previous": float(previous),
                }
            )

        tasks = [fetch_one(base, full) for base, full in symbols]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        return results

    def _normalize_config(self, config: OiRankConfig) -> OiRankConfig:
        refresh = _clamp(config.refresh_interval_minutes, MIN_REFRESH_MINUTES, MAX_REFRESH_MINUTES)
        stale = max(int(config.stale_ttl_minutes), refresh)
        return OiRankConfig(
            refresh_interval_minutes=refresh,
            stale_ttl_minutes=stale,
            created_at=config.created_at,
            updated_at=config.updated_at,
        )


def _normalize_interval(interval: str) -> str:
    value = (interval or "").strip().lower()
    if value not in SUPPORTED_INTERVALS:
        return "1h"
    return value


def _normalize_metric(metric: Optional[str]) -> str:
    value = (metric or "abs").strip().lower()
    if value not in SUPPORTED_METRICS:
        return "abs"
    return value


def _normalize_direction(direction: str) -> str:
    value = (direction or "top").strip().lower()
    if value not in SUPPORTED_DIRECTIONS:
        return "top"
    return value


def _normalize_limit(limit: Optional[int]) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    try:
        parsed = int(limit)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    return max(1, min(parsed, MAX_CACHE_LIMIT))


def _is_hard_stale(updated_at: Optional[datetime], now: datetime, stale_minutes: int) -> bool:
    if updated_at is None:
        return True
    return (now - updated_at).total_seconds() / 60 > stale_minutes


def _is_soft_stale(updated_at: Optional[datetime], now: datetime, refresh_minutes: int, stale_minutes: int) -> bool:
    if updated_at is None:
        return False
    age = (now - updated_at).total_seconds() / 60
    return refresh_minutes < age <= stale_minutes


def _build_rank_entries(items: List[dict]) -> List[OiRankEntry]:
    ranked: List[OiRankEntry] = []
    for index, item in enumerate(items[:MAX_CACHE_LIMIT], start=1):
        symbol = item.get("symbol")
        delta = item.get("delta")
        if not isinstance(symbol, str) or symbol == "":
            continue
        if delta is None:
            continue
        ranked.append(
            OiRankEntry(
                symbol=symbol,
                rank=index,
                delta=float(delta),
                delta_pct=_safe_float(item.get("delta_pct")),
                current=_safe_float(item.get("current")),
                previous=_safe_float(item.get("previous")),
            )
        )
    return ranked


def _safe_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _strip_usdt(symbol: str) -> str:
    value = symbol.strip().upper()
    if value.endswith("USDT"):
        return value[: -4]
    return value


def _clamp(value: int, min_value: int, max_value: int) -> int:
    return max(min_value, min(max_value, int(value)))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
