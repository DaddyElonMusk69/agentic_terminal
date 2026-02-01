from datetime import datetime, timezone
import asyncio
import inspect
import time
from typing import Awaitable, Callable, Dict, List, Optional

from app.domain.ema_scanner.models import EmaScannerConfig, EmaScannerSignal
from app.domain.portfolio.models import MarketCandle
from app.infrastructure.external.binance_client import BinanceClient


LogCallback = Callable[[str, Optional[dict]], Awaitable[None] | None]
_EMA_INTERVAL_DELAY_SEC = 0.2


async def _emit_log(
    log_callback: Optional[LogCallback],
    event: str,
    data: Optional[dict] = None,
) -> None:
    if not log_callback:
        return
    result = log_callback(event, data)
    if inspect.isawaitable(result):
        await result


class EmaScannerService:
    """Scan assets for EMA proximity signals using Binance public market data."""

    def __init__(
        self,
        portfolio_service,
        binance_client: Optional[BinanceClient] = None,
    ) -> None:
        self._portfolio_service = portfolio_service
        self._binance_client = binance_client or BinanceClient()

    async def scan(
        self,
        config: EmaScannerConfig,
        log_callback: Optional[LogCallback] = None,
        chart_store: Optional[Dict[str, Dict[str, dict]]] = None,
    ) -> List[EmaScannerSignal]:
        if not config.assets or not config.timeframes or not config.ema_lengths:
            return []

        signals: List[EmaScannerSignal] = []

        max_ema = max(config.ema_lengths)
        candles_needed = min(max(max_ema, 20) * 3, config.max_candles)

        data_source = await self._resolve_exchange_label()

        for asset in config.assets:
            symbol = self._normalize_symbol(asset, config.quote_asset)
            asset_label = asset.strip().upper()
            ema_votes = 0
            bb_votes = 0

            await _emit_log(
                log_callback,
                "scan_start_asset",
                {"symbol": asset_label, "source": data_source},
            )

            try:
                try:
                    live_price = await asyncio.to_thread(
                        self._binance_client.fetch_ticker_price,
                        symbol,
                    )
                except Exception:
                    live_price = None
                if live_price is None:
                    await _emit_log(
                        log_callback,
                        "scan_no_price",
                        {"symbol": asset_label},
                    )
                for timeframe in config.timeframes:
                    try:
                        await _emit_log(
                            log_callback,
                            "scan_interval_check",
                            {"interval": timeframe, "symbol": asset_label},
                        )
                        interval_ms = _interval_to_ms(timeframe)
                        if interval_ms <= 0:
                            await _emit_log(
                                log_callback,
                                "scan_invalid_interval",
                                {"interval": timeframe},
                            )
                            continue
                        start_time_ms = int(time.time() * 1000) - (interval_ms * candles_needed)
                        candles = await asyncio.to_thread(
                            self._binance_client.fetch_candles,
                            symbol,
                            timeframe,
                            candles_needed,
                            start_time_ms,
                        )
                        if not candles:
                            await _emit_log(
                                log_callback,
                                "scan_fetch_failed",
                                {"interval": timeframe, "source": data_source},
                            )
                            continue

                        if live_price is not None:
                            candles = _apply_live_price(candles, float(live_price))

                        interval_has_vote = False
                        closes = [c.close for c in candles]
                        price = float(live_price) if live_price is not None else float(closes[-1])
                        timestamp = datetime.now(timezone.utc)

                        if len(closes) < 20:
                            await _emit_log(
                                log_callback,
                                "scan_short_series",
                                {"interval": timeframe, "candles": len(closes)},
                            )

                        skipped_ema = [length for length in config.ema_lengths if len(closes) < length]
                        if skipped_ema:
                            await _emit_log(
                                log_callback,
                                "scan_skip_ema",
                                {
                                    "interval": timeframe,
                                    "candles": len(closes),
                                    "lengths": skipped_ema,
                                },
                            )

                        for length in config.ema_lengths:
                            if len(closes) < length:
                                continue
                            ema_value = _ema(closes, length)
                            if ema_value is None:
                                continue

                            lower_bound = ema_value * (1 - config.tolerance_pct / 100)
                            upper_bound = ema_value * (1 + config.tolerance_pct / 100)

                            if lower_bound <= price <= upper_bound:
                                ema_votes += 1
                                interval_has_vote = True
                                await _emit_log(
                                    log_callback,
                                    "scan_ema_hit",
                                    {
                                        "interval": timeframe,
                                        "length": length,
                                        "price": price,
                                        "ema_value": ema_value,
                                    },
                                )
                                signals.append(
                                    EmaScannerSignal(
                                        symbol=symbol,
                                        timeframe=timeframe,
                                        indicator="EMA",
                                        parameter=f"EMA-{length}",
                                        value=ema_value,
                                        price=price,
                                        lower_bound=lower_bound,
                                        upper_bound=upper_bound,
                                        condition="proximity",
                                        timestamp=timestamp,
                                    )
                                )

                        if len(closes) >= 20:
                            bb = _bollinger_bands(closes, length=20, std_dev=2)
                            if bb is not None:
                                bb_middle, bb_upper, bb_lower = bb
                                upper_tolerance = bb_upper * (config.tolerance_pct / 100)
                                lower_tolerance = bb_lower * (config.tolerance_pct / 100)

                                upper_lower_bound = bb_upper - upper_tolerance
                                upper_upper_bound = bb_upper + upper_tolerance
                                lower_lower_bound = bb_lower - lower_tolerance
                                lower_upper_bound = bb_lower + lower_tolerance

                                distance_upper = abs(price - bb_upper)
                                is_near_upper = distance_upper <= upper_tolerance
                                is_above_upper = price > bb_upper
                                if is_near_upper or is_above_upper:
                                    bb_votes += 1
                                    interval_has_vote = True
                                    signals.append(
                                        EmaScannerSignal(
                                            symbol=symbol,
                                            timeframe=timeframe,
                                            indicator="BB",
                                            parameter="BB-Upper",
                                            value=bb_upper,
                                            price=price,
                                            lower_bound=upper_lower_bound,
                                            upper_bound=upper_upper_bound,
                                            condition="breakout" if is_above_upper else "proximity",
                                            timestamp=timestamp,
                                        )
                                    )

                                distance_lower = abs(price - bb_lower)
                                is_near_lower = distance_lower <= lower_tolerance
                                is_below_lower = price < bb_lower
                                if is_near_lower or is_below_lower:
                                    bb_votes += 1
                                    interval_has_vote = True
                                    signals.append(
                                        EmaScannerSignal(
                                            symbol=symbol,
                                            timeframe=timeframe,
                                            indicator="BB",
                                            parameter="BB-Lower",
                                            value=bb_lower,
                                            price=price,
                                            lower_bound=lower_lower_bound,
                                            upper_bound=lower_upper_bound,
                                            condition="breakdown" if is_below_lower else "proximity",
                                            timestamp=timestamp,
                                        )
                                    )
                        else:
                            await _emit_log(
                                log_callback,
                                "scan_skip_bb",
                                {"interval": timeframe, "candles": len(closes)},
                            )

                        if interval_has_vote and chart_store is not None:
                            payload = _build_chart_payload(candles, config.ema_lengths)
                            if payload.get("candles"):
                                chart_store.setdefault(symbol, {})[timeframe] = payload
                    finally:
                        if _EMA_INTERVAL_DELAY_SEC > 0:
                            await asyncio.sleep(_EMA_INTERVAL_DELAY_SEC)
            except Exception as exc:
                await _emit_log(
                    log_callback,
                    "scan_error",
                    {"symbol": asset_label, "error": str(exc)},
                )
                continue

            await _emit_log(
                log_callback,
                "scan_asset_complete",
                {"symbol": asset_label, "ema_votes": ema_votes, "bb_votes": bb_votes},
            )

        return signals

    def _normalize_symbol(self, asset: str, quote_asset: str) -> str:
        asset = asset.strip().upper()
        if "/" in asset or ":" in asset:
            return asset
        return f"{asset}/{quote_asset}"

    async def _resolve_exchange_label(self) -> str:
        return "BINANCE FUTURES (PUBLIC)"


def _ema(values: List[float], length: int) -> float | None:
    if length <= 0 or len(values) < length:
        return None
    if length == 1:
        return values[-1]

    sma = sum(values[:length]) / length
    multiplier = 2 / (length + 1)
    ema = sma

    for price in values[length:]:
        ema = (price - ema) * multiplier + ema

    return ema


def _interval_to_ms(interval_str: str) -> int:
    if not interval_str or len(interval_str) < 2:
        return 0
    unit = interval_str[-1]
    try:
        value = int(interval_str[:-1])
    except ValueError:
        return 0
    if unit == "m":
        return value * 60 * 1000
    if unit == "h":
        return value * 60 * 60 * 1000
    if unit == "d":
        return value * 24 * 60 * 60 * 1000
    return 0


def _apply_live_price(candles: List[MarketCandle], live_price: float) -> List[MarketCandle]:
    if not candles:
        return candles
    last = candles[-1]
    if last.close == live_price:
        return candles
    updated = list(candles)
    updated[-1] = MarketCandle(
        timestamp_ms=last.timestamp_ms,
        open=last.open,
        high=last.high,
        low=last.low,
        close=live_price,
        volume=last.volume,
    )
    return updated


def _bollinger_bands(values: List[float], length: int, std_dev: float) -> tuple[float, float, float] | None:
    if length <= 0 or len(values) < length:
        return None
    window = values[-length:]
    mean = sum(window) / length
    variance = sum((price - mean) ** 2 for price in window) / length
    std = variance ** 0.5
    upper = mean + std_dev * std
    lower = mean - std_dev * std
    return mean, upper, lower


def _ema_series(values: List[float], length: int) -> List[float | None]:
    if length <= 0 or len(values) < length:
        return []
    ema_values: List[float | None] = [None] * len(values)
    sma = sum(values[:length]) / length
    multiplier = 2 / (length + 1)
    ema = sma
    ema_values[length - 1] = ema
    for idx in range(length, len(values)):
        ema = (values[idx] - ema) * multiplier + ema
        ema_values[idx] = ema
    return ema_values


def _bollinger_series(
    values: List[float],
    length: int,
    std_dev: float,
) -> tuple[List[float | None], List[float | None], List[float | None]]:
    if length <= 0 or len(values) < length:
        return [], [], []
    middle: List[float | None] = [None] * len(values)
    upper: List[float | None] = [None] * len(values)
    lower: List[float | None] = [None] * len(values)
    for idx in range(length - 1, len(values)):
        window = values[idx - length + 1 : idx + 1]
        mean = sum(window) / length
        variance = sum((price - mean) ** 2 for price in window) / length
        std = variance ** 0.5
        middle[idx] = mean
        upper[idx] = mean + std_dev * std
        lower[idx] = mean - std_dev * std
    return middle, upper, lower


def _build_chart_payload(candles, ema_lengths: List[int]) -> dict:
    if not candles:
        return {}
    total = len(candles)
    start_idx = max(0, total - 50)

    candle_payload = [
        {
            "time": int(candle.timestamp_ms / 1000),
            "open": float(candle.open),
            "high": float(candle.high),
            "low": float(candle.low),
            "close": float(candle.close),
        }
        for candle in candles[start_idx:]
    ]

    closes = [candle.close for candle in candles]

    ema_payload: Dict[str, List[dict]] = {}
    for length in ema_lengths:
        series = _ema_series(closes, length)
        if not series:
            continue
        points: List[dict] = []
        for idx in range(start_idx, total):
            value = series[idx]
            if value is None:
                continue
            points.append(
                {
                    "time": int(candles[idx].timestamp_ms / 1000),
                    "value": float(value),
                }
            )
        if points:
            ema_payload[str(length)] = points

    mid_series, upper_series, lower_series = _bollinger_series(closes, length=20, std_dev=2)
    bb_upper: List[dict] = []
    bb_middle: List[dict] = []
    bb_lower: List[dict] = []
    if mid_series:
        for idx in range(start_idx, total):
            timestamp = int(candles[idx].timestamp_ms / 1000)
            if upper_series[idx] is not None:
                bb_upper.append({"time": timestamp, "value": float(upper_series[idx])})
            if mid_series[idx] is not None:
                bb_middle.append({"time": timestamp, "value": float(mid_series[idx])})
            if lower_series[idx] is not None:
                bb_lower.append({"time": timestamp, "value": float(lower_series[idx])})

    return {
        "candles": candle_payload,
        "emas": ema_payload,
        "bollinger": {
            "upper": bb_upper,
            "middle": bb_middle,
            "lower": bb_lower,
        },
    }
