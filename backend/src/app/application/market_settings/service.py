import importlib
import logging
from datetime import date, datetime, time, timezone
from functools import lru_cache
from typing import Any, List
from zoneinfo import ZoneInfo

from app.domain.market_settings.interfaces import MarketSettingsRepository


DEFAULT_ASSETS = ["BTC"]
DEFAULT_INTERVALS: List[str] = []
US_STOCK_MARKET_TIMEZONE = ZoneInfo("America/New_York")
US_STOCK_MARKET_OPEN = time(hour=9, minute=30)
US_STOCK_MARKET_CLOSE = time(hour=16, minute=0)

logger = logging.getLogger(__name__)
_warned_missing_market_calendar = False


class MarketSettingsService:
    def __init__(self, repository: MarketSettingsRepository) -> None:
        self._repository = repository

    async def list_assets(self) -> List[str]:
        assets = await self._repository.list_assets()
        if not assets:
            for symbol in DEFAULT_ASSETS:
                await self._repository.add_asset(symbol)
            assets = await self._repository.list_assets()
        return assets

    async def list_us_stock_assets(self) -> List[str]:
        return await self._repository.list_us_stock_assets()

    async def list_intervals(self) -> List[str]:
        intervals = await self._repository.list_intervals()
        if not intervals:
            for interval in DEFAULT_INTERVALS:
                await self._repository.add_interval(interval)
            intervals = await self._repository.list_intervals()
        return intervals

    async def add_asset(self, symbol: str) -> List[str]:
        normalized = symbol.strip().upper()
        if normalized:
            await self._repository.add_asset(normalized)
        return await self.list_assets()

    async def add_us_stock_asset(self, symbol: str) -> List[str]:
        normalized = symbol.strip().upper()
        if normalized:
            await self._repository.add_us_stock_asset(normalized)
        return await self.list_us_stock_assets()

    async def remove_asset(self, symbol: str) -> List[str]:
        normalized = symbol.strip().upper()
        if normalized:
            await self._repository.remove_asset(normalized)
        return await self.list_assets()

    async def remove_us_stock_asset(self, symbol: str) -> List[str]:
        normalized = symbol.strip().upper()
        if normalized:
            await self._repository.remove_us_stock_asset(normalized)
        return await self.list_us_stock_assets()

    async def add_interval(self, interval: str) -> List[str]:
        normalized = interval.strip().lower()
        if normalized:
            await self._repository.add_interval(normalized)
        return await self.list_intervals()

    async def remove_interval(self, interval: str) -> List[str]:
        normalized = interval.strip().lower()
        if normalized:
            await self._repository.remove_interval(normalized)
        return await self.list_intervals()

    def is_us_stock_market_open(self, now: datetime | None = None) -> bool:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        current_utc = current.astimezone(timezone.utc)
        eastern = current_utc.astimezone(US_STOCK_MARKET_TIMEZONE)

        calendar = _load_us_stock_market_calendar()
        if calendar is not None:
            session = _get_us_stock_market_session_bounds(eastern.date())
            if session is None:
                return False
            market_open, market_close = session
            return market_open <= current_utc < market_close

        if eastern.weekday() >= 5:
            return False
        current_time = eastern.timetz().replace(tzinfo=None)
        return US_STOCK_MARKET_OPEN <= current_time < US_STOCK_MARKET_CLOSE


@lru_cache(maxsize=1)
def _load_us_stock_market_calendar() -> Any | None:
    global _warned_missing_market_calendar

    try:
        market_calendars = importlib.import_module("pandas_market_calendars")
    except ModuleNotFoundError:
        if not _warned_missing_market_calendar:
            logger.warning(
                "pandas_market_calendars is not installed; falling back to weekday/time checks "
                "for US stock session assets."
            )
            _warned_missing_market_calendar = True
        return None

    return market_calendars.get_calendar("NYSE")


@lru_cache(maxsize=128)
def _get_us_stock_market_session_bounds(
    session_date: date,
) -> tuple[datetime, datetime] | None:
    calendar = _load_us_stock_market_calendar()
    if calendar is None:
        return None

    schedule = calendar.schedule(
        start_date=session_date.isoformat(),
        end_date=session_date.isoformat(),
    )
    if schedule is None or schedule.empty:
        return None

    session = schedule.iloc[0]
    market_open = _coerce_session_datetime(session.get("market_open"))
    market_close = _coerce_session_datetime(session.get("market_close"))
    if market_open is None or market_close is None:
        return None
    return market_open, market_close


def _coerce_session_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    to_pydatetime = getattr(value, "to_pydatetime", None)
    if callable(to_pydatetime):
        resolved = to_pydatetime()
        if isinstance(resolved, datetime):
            return resolved if resolved.tzinfo is not None else resolved.replace(tzinfo=timezone.utc)
    return None
