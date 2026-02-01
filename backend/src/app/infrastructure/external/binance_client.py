from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
from collections import deque
from datetime import datetime, timezone
from http.client import IncompleteRead
from typing import Any, List, Optional

import certifi
import httpx

from app.settings import get_settings

from app.domain.portfolio.models import (
    FundingRateSnapshot,
    MarketCandle,
    MarketDataPoint,
    OrderBookLevel,
    OrderBookSnapshot,
)

logger = logging.getLogger(__name__)


class BinanceClient:
    BASE_URL = "https://fapi.binance.com"
    DATA_URL = "https://fapi.binance.com/futures/data"
    DEFAULT_TIMEOUT = 10
    MAX_KLINES_LIMIT = 1500
    DEFAULT_MAX_RPS = 5
    DEFAULT_MAX_CONCURRENCY = 2
    DEFAULT_RETRY_COUNT = 2
    DEFAULT_RETRY_BASE_DELAY = 0.5
    DEFAULT_RETRY_MAX_DELAY = 4.0
    DEFAULT_RETRY_JITTER = 0.3
    DEFAULT_RATE_LIMIT_BACKOFF = 15.0
    VALID_OI_INTERVALS = {
        "5m",
        "15m",
        "30m",
        "1h",
        "2h",
        "4h",
        "6h",
        "12h",
        "1d",
    }
    VALID_DEPTH_LIMITS = (5, 10, 20, 50, 100, 500, 1000)
    _rate_lock = threading.Lock()
    _rate_timestamps = deque()
    _rate_configured = False
    _concurrency_sem = threading.Semaphore(DEFAULT_MAX_CONCURRENCY)
    _max_rps = DEFAULT_MAX_RPS
    _max_concurrency = DEFAULT_MAX_CONCURRENCY
    _retry_count = DEFAULT_RETRY_COUNT
    _retry_base_delay = DEFAULT_RETRY_BASE_DELAY
    _retry_max_delay = DEFAULT_RETRY_MAX_DELAY
    _retry_jitter = DEFAULT_RETRY_JITTER
    _rate_limit_backoff = DEFAULT_RATE_LIMIT_BACKOFF

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        self._timeout = timeout
        self._last_error: Optional[str] = None
        verify = False if _allow_insecure_ssl() else certifi.where()
        self._client = httpx.Client(
            timeout=self._timeout,
            headers={
                "Accept": "application/json",
                "User-Agent": "TradingDashboard/1.0",
            },
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            verify=verify,
        )
        self._ensure_rate_config()

    def fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
        start_time_ms: Optional[int] = None,
        end_time_ms: Optional[int] = None,
    ) -> List[MarketCandle]:
        limit_value = _clamp_int(limit, 1, self.MAX_KLINES_LIMIT)
        params = {
            "symbol": self._to_binance_symbol(symbol),
            "interval": timeframe,
            "limit": limit_value,
        }
        if start_time_ms is not None:
            params["startTime"] = int(start_time_ms)
        if end_time_ms is not None:
            params["endTime"] = int(end_time_ms)
        data = self._get_json(f"{self.BASE_URL}/fapi/v1/klines", params)
        if not isinstance(data, list):
            if self._last_error is None:
                self._last_error = "invalid response"
            return []

        candles: List[MarketCandle] = []
        for row in data:
            if not isinstance(row, list) or len(row) < 6:
                continue
            timestamp_ms = _to_timestamp_ms(row[0])
            open_price = _to_float(row[1])
            high = _to_float(row[2])
            low = _to_float(row[3])
            close = _to_float(row[4])
            volume = _to_float(row[5])
            if None in (timestamp_ms, open_price, high, low, close, volume):
                continue
            candles.append(
                MarketCandle(
                    timestamp_ms=timestamp_ms,
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume,
                )
            )
        if not candles and self._last_error is None:
            self._last_error = "empty response"
        return candles

    def fetch_ticker_price(self, symbol: str) -> Optional[float]:
        params = {"symbol": self._to_binance_symbol(symbol)}
        data = self._get_json(f"{self.BASE_URL}/fapi/v1/ticker/price", params)
        if not isinstance(data, dict):
            if self._last_error is None:
                self._last_error = "invalid response"
            return None
        price = _to_float(data.get("price"))
        if price is None:
            if self._last_error is None:
                self._last_error = "missing price"
            return None
        return price

    def fetch_order_book(self, symbol: str, limit: int = 50) -> Optional[OrderBookSnapshot]:
        depth_limit = _normalize_depth_limit(limit, self.VALID_DEPTH_LIMITS)
        params = {
            "symbol": self._to_binance_symbol(symbol),
            "limit": depth_limit,
        }
        data = self._get_json(f"{self.BASE_URL}/fapi/v1/depth", params)
        if not isinstance(data, dict):
            if self._last_error is None:
                self._last_error = "invalid response"
            return None

        bids: List[OrderBookLevel] = []
        for level in data.get("bids", []):
            if not isinstance(level, list) or len(level) < 2:
                continue
            price = _to_float(level[0])
            size = _to_float(level[1])
            if price is None or size is None:
                continue
            bids.append(OrderBookLevel(price=price, size=size))

        asks: List[OrderBookLevel] = []
        for level in data.get("asks", []):
            if not isinstance(level, list) or len(level) < 2:
                continue
            price = _to_float(level[0])
            size = _to_float(level[1])
            if price is None or size is None:
                continue
            asks.append(OrderBookLevel(price=price, size=size))
        timestamp_ms = _to_timestamp_ms(data.get("E") or data.get("T"))
        if timestamp_ms is None:
            timestamp_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        return OrderBookSnapshot(
            symbol=symbol,
            timestamp_ms=timestamp_ms,
            bids=bids,
            asks=asks,
        )

    def fetch_open_interest_history(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> List[MarketDataPoint]:
        interval = timeframe if timeframe in self.VALID_OI_INTERVALS else "15m"
        params = {
            "symbol": self._to_binance_symbol(symbol),
            "period": interval,
            "limit": min(limit, 500),
        }
        data = self._get_json(f"{self.DATA_URL}/openInterestHist", params)
        if not isinstance(data, list):
            if self._last_error is None:
                self._last_error = "invalid response"
            return []

        points: List[MarketDataPoint] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            value = _to_float(
                entry.get("sumOpenInterestValue")
                or entry.get("sumOpenInterest")
                or entry.get("openInterest")
            )
            timestamp_ms = _to_timestamp_ms(entry.get("timestamp") or entry.get("time"))
            if value is None:
                continue
            if timestamp_ms is None:
                timestamp_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            points.append(MarketDataPoint(timestamp_ms=timestamp_ms, value=value))
        if not points and self._last_error is None:
            self._last_error = "empty response"
        return points

    def fetch_funding_rate(self, symbol: str) -> Optional[FundingRateSnapshot]:
        params = {"symbol": self._to_binance_symbol(symbol)}
        data = self._get_json(f"{self.BASE_URL}/fapi/v1/premiumIndex", params)
        if not isinstance(data, dict):
            if self._last_error is None:
                self._last_error = "invalid response"
            return None

        rate = _to_float(data.get("lastFundingRate") or data.get("fundingRate"))
        if rate is None:
            if self._last_error is None:
                self._last_error = "missing funding rate"
            return None
        rate = max(-0.01, min(0.01, rate))

        timestamp_ms = _to_timestamp_ms(data.get("time") or data.get("timestamp"))
        if timestamp_ms is None:
            timestamp_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        next_funding = _to_timestamp_ms(data.get("nextFundingTime"))
        mark_price = _to_float(data.get("markPrice") or data.get("mark_price"))

        return FundingRateSnapshot(
            rate=rate,
            timestamp_ms=timestamp_ms,
            next_funding_time_ms=next_funding,
            mark_price=mark_price,
        )

    def consume_last_error(self) -> Optional[str]:
        error = self._last_error
        self._last_error = None
        return error

    def _get_json(self, url: str, params: dict[str, Any]) -> Optional[Any]:
        max_attempts = max(1, self._retry_count + 1)
        for attempt in range(1, max_attempts + 1):
            self._last_error = None
            try:
                with self._concurrency_sem:
                    self._throttle()
                    response = self._client.get(url, params=params)
                payload = response.text
                if response.status_code != 200:
                    self._last_error = f"http {response.status_code}"
                    retryable = _is_retryable_http(response.status_code)
                    logger.warning(
                        "Binance API HTTP error %s for %s params=%s payload=%s",
                        response.status_code,
                        url,
                        params,
                        payload[:200],
                    )
                    if retryable and attempt < max_attempts:
                        delay = self._retry_delay(
                            attempt,
                            is_rate_limit=response.status_code in {418, 429},
                        )
                        time.sleep(delay)
                        continue
                    return None
                data = json.loads(payload)
                if isinstance(data, dict) and "code" in data:
                    code = data.get("code")
                    message = data.get("msg", "unknown error")
                    if code == -1121:
                        self._last_error = "invalid symbol"
                        logger.debug("Binance API invalid symbol: %s params=%s", message, params)
                        return None
                    if code == -1003 and attempt < max_attempts:
                        delay = self._retry_delay(attempt, is_rate_limit=True)
                        logger.warning(
                            "Binance API rate limit (code %s). Retrying in %.2fs params=%s",
                            code,
                            delay,
                            params,
                        )
                        time.sleep(delay)
                        continue
                    self._last_error = f"api error {code}: {message}"
                    logger.warning("Binance API error: %s params=%s", message, params)
                    return None
                return data
            except (httpx.TimeoutException, httpx.ReadError, httpx.RemoteProtocolError, httpx.RequestError, IncompleteRead, TimeoutError) as exc:
                self._last_error = f"network error: {exc}"
                logger.warning("Binance API network error for %s params=%s error=%s", url, params, exc)
                if attempt < max_attempts:
                    time.sleep(self._retry_delay(attempt))
                    continue
                return None
            except (json.JSONDecodeError, ValueError) as exc:
                self._last_error = "invalid json"
                logger.warning("Binance API invalid JSON for %s params=%s error=%s", url, params, exc)
                if attempt < max_attempts:
                    time.sleep(self._retry_delay(attempt))
                    continue
                return None
            except Exception as exc:
                self._last_error = "unexpected error"
                logger.warning("Binance API unexpected error for %s params=%s error=%s", url, params, exc)
                if attempt < max_attempts:
                    time.sleep(self._retry_delay(attempt))
                    continue
                return None
        return None

    def _to_binance_symbol(self, symbol: str) -> str:
        clean = (
            symbol.upper()
            .replace("-PERP", "")
            .replace("PERP", "")
            .replace("USDT", "")
            .replace("/", "")
            .replace("-", "")
            .replace(":", "")
        )
        return f"{clean}USDT"

    @classmethod
    def _ensure_rate_config(cls) -> None:
        if cls._rate_configured:
            return
        settings = get_settings()
        cls._max_rps = max(1, int(getattr(settings, "binance_max_requests_per_second", cls.DEFAULT_MAX_RPS)))
        cls._max_concurrency = max(
            1, int(getattr(settings, "binance_max_concurrency", cls.DEFAULT_MAX_CONCURRENCY))
        )
        cls._retry_count = max(0, int(getattr(settings, "binance_retry_count", cls.DEFAULT_RETRY_COUNT)))
        cls._retry_base_delay = float(
            getattr(settings, "binance_retry_base_delay", cls.DEFAULT_RETRY_BASE_DELAY)
        )
        cls._retry_max_delay = float(
            getattr(settings, "binance_retry_max_delay", cls.DEFAULT_RETRY_MAX_DELAY)
        )
        cls._retry_jitter = float(getattr(settings, "binance_retry_jitter", cls.DEFAULT_RETRY_JITTER))
        cls._rate_limit_backoff = float(
            getattr(settings, "binance_rate_limit_backoff", cls.DEFAULT_RATE_LIMIT_BACKOFF)
        )
        cls._concurrency_sem = threading.Semaphore(cls._max_concurrency)
        cls._rate_configured = True

    @classmethod
    def _throttle(cls) -> None:
        if cls._max_rps <= 0:
            return
        while True:
            now = time.monotonic()
            with cls._rate_lock:
                while cls._rate_timestamps and now - cls._rate_timestamps[0] >= 1.0:
                    cls._rate_timestamps.popleft()
                if len(cls._rate_timestamps) < cls._max_rps:
                    cls._rate_timestamps.append(now)
                    return
                wait = 1.0 - (now - cls._rate_timestamps[0])
            if wait > 0:
                time.sleep(wait + random.uniform(0, cls._retry_jitter))

    @classmethod
    def _retry_delay(cls, attempt: int, is_rate_limit: bool = False) -> float:
        delay = cls._retry_base_delay * (2 ** (attempt - 1))
        delay = min(delay, cls._retry_max_delay)
        if is_rate_limit:
            delay = max(delay, cls._rate_limit_backoff)
        return delay + random.uniform(0, cls._retry_jitter)


def _is_retryable_http(status_code: int) -> bool:
    if status_code in {418, 429}:
        return True
    return 500 <= status_code <= 599


def _allow_insecure_ssl() -> bool:
    return bool(_get_env_flag("ALLOW_INSECURE_SSL"))


def _get_env_flag(name: str) -> bool:
    value = (os.environ.get(name) or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_timestamp_ms(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return int(parsed.timestamp() * 1000)
    if isinstance(value, datetime):
        return int(value.timestamp() * 1000)
    return None


def _normalize_depth_limit(limit: int, allowed: tuple[int, ...]) -> int:
    if limit <= 0:
        return allowed[0]
    for candidate in allowed:
        if limit <= candidate:
            return candidate
    return allowed[-1]


def _clamp_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return minimum
    return max(minimum, min(numeric, maximum))
