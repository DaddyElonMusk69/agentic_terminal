from __future__ import annotations

from datetime import datetime, timezone
import asyncio
import inspect
from typing import Awaitable, Callable, Dict, List, Optional, Tuple

from app.application.portfolio.dependencies import get_portfolio_service
from app.application.quant_scanner.netflow_service import NetflowService
from app.domain.quant_scanner.calculations import (
    calculate_cvd_from_candles,
    calculate_depth_metrics,
    calculate_vwap_metrics,
    calculate_atr_metrics,
    calculate_slope_with_zscore,
    analyze_anomalies,
)
from app.domain.quant_scanner.models import QuantScannerConfig, QuantSnapshot
from app.infrastructure.external.binance_client import BinanceClient


DEFAULT_ORDER_BOOK_LIMIT = 50
DEFAULT_DEPTH_RANGE_PCT = 0.5
DEFAULT_SLOPE_WINDOW = 6
DEFAULT_ANOMALY_WINDOW = 20
DEFAULT_ATR_PERIOD = 14
DEFAULT_ATR_LOOKBACK = 100
DEFAULT_ATR_SLOPE_WINDOW = 5


LogCallback = Callable[[str, str], Awaitable[None] | None]
SnapshotCallback = Callable[[QuantSnapshot], Awaitable[None] | None]
CancelCheck = Callable[[], bool]


async def _emit_log(
    log_callback: Optional[LogCallback],
    message: str,
    log_type: str,
) -> None:
    if not log_callback:
        return
    result = log_callback(message, log_type)
    if inspect.isawaitable(result):
        await result


async def _emit_snapshot(
    snapshot_callback: Optional[SnapshotCallback],
    snapshot: QuantSnapshot,
) -> None:
    if not snapshot_callback:
        return
    result = snapshot_callback(snapshot)
    if inspect.isawaitable(result):
        await result


async def _raise_if_cancelled(cancel_check: Optional[CancelCheck]) -> None:
    if cancel_check and cancel_check():
        raise asyncio.CancelledError()


def _format_number(value: Optional[float], decimals: int = 2) -> str:
    if value is None:
        return "--"
    return f"{value:,.{decimals}f}"


def _format_usd(value: Optional[float], decimals: int = 2) -> str:
    if value is None:
        return "--"
    return f"${value:,.{decimals}f}"


def _format_percent(value: Optional[float], decimals: int = 2) -> str:
    if value is None:
        return "--"
    return f"{value:+.{decimals}f}%"


class QuantDataCache:
    def __init__(self) -> None:
        self._entries: Dict[Tuple[str, str], QuantSnapshot] = {}

    def set(self, snapshot: QuantSnapshot) -> None:
        key = (_normalize_symbol(snapshot.symbol), snapshot.timeframe)
        self._entries[key] = snapshot

    def get(self, symbol: str, timeframe: str) -> Optional[QuantSnapshot]:
        return self._entries.get((_normalize_symbol(symbol), timeframe))

    def all(self) -> List[QuantSnapshot]:
        return list(self._entries.values())

    def clear(self) -> None:
        self._entries.clear()

    def clear_symbol(self, symbol: str) -> None:
        normalized = _normalize_symbol(symbol)
        for key in list(self._entries.keys()):
            if key[0] == normalized:
                del self._entries[key]


class QuantScannerService:
    def __init__(
        self,
        cache: Optional[QuantDataCache] = None,
        portfolio_service=None,
        netflow_service: Optional[NetflowService] = None,
        binance_client: Optional[BinanceClient] = None,
    ) -> None:
        self._portfolio_service = portfolio_service or get_portfolio_service()
        self._cache = cache or QuantDataCache()
        self._netflow_service = netflow_service or NetflowService()
        self._binance_client = binance_client or BinanceClient()

    async def scan(
        self,
        config: QuantScannerConfig,
        limit: int = 200,
        log_callback: Optional[LogCallback] = None,
        snapshot_callback: Optional[SnapshotCallback] = None,
        cancel_check: Optional[CancelCheck] = None,
    ) -> List[QuantSnapshot]:
        if not config.assets or not config.timeframes:
            return []

        snapshots: List[QuantSnapshot] = []
        candles_needed = max(limit, 3)

        total_scans = len(config.assets) * len(config.timeframes)
        scan_count = 0

        for asset in config.assets:
            await _raise_if_cancelled(cancel_check)
            symbol = _normalize_asset(asset, config.quote_asset)
            if not symbol:
                continue

            funding_rate = None
            depth_metrics = None
            raw_netflow = None

            try:
                order_book = await asyncio.to_thread(
                    self._binance_client.fetch_order_book,
                    symbol,
                    DEFAULT_ORDER_BOOK_LIMIT,
                )
            except Exception:
                order_book = None

            if order_book:
                depth_metrics = calculate_depth_metrics(
                    order_book, range_pct=DEFAULT_DEPTH_RANGE_PCT
                )
            if depth_metrics:
                await _emit_log(
                    log_callback,
                    "  depth: bid {bid} ask {ask} net {net} imbalance {imbalance}".format(
                        bid=_format_usd(depth_metrics.bid_volume_usd, 0),
                        ask=_format_usd(depth_metrics.ask_volume_usd, 0),
                        net=_format_usd(depth_metrics.net_depth_usd, 0),
                        imbalance=_format_percent(depth_metrics.imbalance_pct, 2),
                    ),
                    "calc",
                )
            else:
                await _emit_log(
                    log_callback,
                    "  depth: unavailable",
                    "warning",
                )

            try:
                funding_rate = await asyncio.to_thread(
                    self._binance_client.fetch_funding_rate,
                    symbol,
                )
            except Exception:
                funding_rate = None
            if funding_rate is None:
                error = self._binance_client.consume_last_error() or "no data"
                await _emit_log(
                    log_callback,
                    f"  funding: Binance public feed error ({error}) [{symbol}]",
                    "warning",
                )
            if funding_rate:
                rate_pct = funding_rate.rate * 100
                await _emit_log(
                    log_callback,
                    "  funding: rate {rate:.6f} ({rate_pct:.4f}%), mark {mark}".format(
                        rate=funding_rate.rate,
                        rate_pct=rate_pct,
                        mark=_format_usd(funding_rate.mark_price, 2),
                    ),
                    "info",
                )
            else:
                await _emit_log(
                    log_callback,
                    "  funding: unavailable",
                    "warning",
                )

            netflow_enabled = self._netflow_service.is_enabled()
            if netflow_enabled:
                await _raise_if_cancelled(cancel_check)
                raw_netflow = await self._netflow_service.fetch_raw(symbol)
                await _raise_if_cancelled(cancel_check)
                if raw_netflow is None and not self._netflow_service.is_configured():
                    await _emit_log(
                        log_callback,
                        "  netflow: missing NofXOS API key",
                        "warning",
                    )
            else:
                await _emit_log(
                    log_callback,
                    "  netflow: disabled (NofXOS deprecated)",
                    "info",
                )

            for timeframe in config.timeframes:
                await _raise_if_cancelled(cancel_check)
                scan_count += 1
                await _emit_log(
                    log_callback,
                    f"[{scan_count}/{total_scans}] {symbol} @ {timeframe}...",
                    "info",
                )
                candles = await asyncio.to_thread(
                    self._binance_client.fetch_candles,
                    symbol,
                    timeframe,
                    candles_needed,
                )
                await _raise_if_cancelled(cancel_check)
                if not candles:
                    await _emit_log(
                        log_callback,
                        f"  ⚠ {symbol}: No candle data ({timeframe})",
                        "warning",
                    )
                    continue

                window_candles = candles[-candles_needed:]
                prices = [candle.close for candle in window_candles]
                price_current = prices[-1] if prices else None
                await _emit_log(
                    log_callback,
                    "  candles: {count} last close {close}".format(
                        count=len(window_candles),
                        close=_format_usd(price_current, 2),
                    ),
                    "fetch",
                )

                cvd_values, cvd_deltas = calculate_cvd_from_candles(window_candles)
                cvd_current = cvd_values[-1] if cvd_values else None
                if cvd_values:
                    await _emit_log(
                        log_callback,
                        "  cvd: current {current} delta {delta}".format(
                            current=_format_number(cvd_current, 0),
                            delta=_format_number(cvd_deltas[-1] if cvd_deltas else None, 0),
                        ),
                        "info",
                    )

                try:
                    oi_points = await asyncio.to_thread(
                        self._binance_client.fetch_open_interest_history,
                        symbol,
                        timeframe,
                        candles_needed,
                    )
                    await _raise_if_cancelled(cancel_check)
                except Exception:
                    oi_points = []
                if not oi_points:
                    error = self._binance_client.consume_last_error() or "no data"
                    await _emit_log(
                        log_callback,
                        f"  oi: Binance public feed error ({error}) [{symbol} {timeframe}]",
                        "warning",
                    )
                oi_current = oi_points[-1].value if oi_points else None
                oi_values = [point.value for point in oi_points]
                oi_delta = None
                oi_delta_pct = None
                if oi_values and oi_current is not None:
                    oi_delta = oi_current - oi_values[0]
                    if oi_values[0]:
                        oi_delta_pct = (oi_delta / oi_values[0]) * 100
                if oi_values:
                    await _emit_log(
                        log_callback,
                        "  oi: points {count} current {current} delta {delta} ({pct})".format(
                            count=len(oi_values),
                            current=_format_usd(oi_current, 0),
                            delta=_format_usd(oi_delta, 0),
                            pct=_format_percent(oi_delta_pct, 2),
                        ),
                        "info",
                    )
                else:
                    await _emit_log(
                        log_callback,
                        "  oi: unavailable",
                        "warning",
                    )

                vwap_metrics = calculate_vwap_metrics(window_candles, price_current)
                if vwap_metrics:
                    await _emit_log(
                        log_callback,
                        "  vwap: value {value} std {std} dist {dist}".format(
                            value=_format_usd(vwap_metrics.value, 2),
                            std=_format_number(vwap_metrics.std_dev, 2),
                            dist=_format_number(vwap_metrics.distance, 2),
                        ),
                        "calc",
                    )
                else:
                    await _emit_log(
                        log_callback,
                        "  vwap: unavailable",
                        "warning",
                    )
                atr_metrics = None
                tf_minutes = _timeframe_minutes(timeframe)
                if tf_minutes is None or tf_minutes >= 120:
                    atr_metrics = calculate_atr_metrics(
                        window_candles,
                        period=DEFAULT_ATR_PERIOD,
                        lookback=DEFAULT_ATR_LOOKBACK,
                        slope_window=DEFAULT_ATR_SLOPE_WINDOW,
                    )
                if atr_metrics:
                    await _emit_log(
                        log_callback,
                        "  atr: value {value} slope {slope} z {z}".format(
                            value=_format_number(atr_metrics.value, 4),
                            slope=_format_percent(atr_metrics.slope_pct, 2),
                            z=_format_number(atr_metrics.z_score, 2),
                        ),
                        "calc",
                    )
                elif tf_minutes is not None and tf_minutes < 120:
                    await _emit_log(
                        log_callback,
                        "  atr: skipped (timeframe < 2h)",
                        "info",
                    )
                else:
                    await _emit_log(
                        log_callback,
                        "  atr: unavailable",
                        "warning",
                    )

                price_slope, price_slope_z = calculate_slope_with_zscore(
                    prices, window_size=DEFAULT_SLOPE_WINDOW
                )
                oi_slope = None
                oi_slope_z = None
                if oi_values:
                    oi_slope, oi_slope_z = calculate_slope_with_zscore(
                        oi_values, window_size=DEFAULT_SLOPE_WINDOW
                    )
                cvd_slope, cvd_slope_z = calculate_slope_with_zscore(
                    cvd_values, window_size=DEFAULT_SLOPE_WINDOW
                )
                await _emit_log(
                    log_callback,
                    "  slopes: price {price} z {price_z} | oi {oi} z {oi_z} | cvd {cvd} z {cvd_z}".format(
                        price=_format_number(price_slope, 2),
                        price_z=_format_number(price_slope_z, 2),
                        oi=_format_number(oi_slope, 2),
                        oi_z=_format_number(oi_slope_z, 2),
                        cvd=_format_number(cvd_slope, 2),
                        cvd_z=_format_number(cvd_slope_z, 2),
                    ),
                    "calc",
                )
                anomaly_window = DEFAULT_ANOMALY_WINDOW
                if prices:
                    anomaly_window = min(DEFAULT_ANOMALY_WINDOW, len(prices))
                anomalies = analyze_anomalies(
                    prices,
                    oi_values,
                    cvd_values,
                    window_size=anomaly_window,
                )

                netflow = (
                    self._netflow_service.build_metrics(raw_netflow, timeframe)
                    if raw_netflow and netflow_enabled
                    else None
                )
                if netflow_enabled and netflow:
                    if netflow.timeframe != timeframe:
                        await _emit_log(
                            log_callback,
                            "  netflow: using {actual} data for {requested}".format(
                                actual=netflow.timeframe,
                                requested=timeframe,
                            ),
                            "info",
                        )
                    await _emit_log(
                        log_callback,
                        "  netflow: total {total} regime {regime} dominant {dominant}".format(
                            total=_format_usd(netflow.total_netflow, 0),
                            regime=netflow.flow_regime,
                            dominant=netflow.dominant_flow,
                        ),
                        "info",
                    )
                elif netflow_enabled:
                    await _emit_log(
                        log_callback,
                        "  netflow: unavailable",
                        "warning",
                    )

                for label, result in [
                    ("price", anomalies.price),
                    ("oi", anomalies.open_interest),
                    ("cvd", anomalies.cvd),
                ]:
                    if result.is_significant:
                        await _emit_log(
                            log_callback,
                            "  anomaly: {label} {atype} z {z} mag {mag}".format(
                                label=label,
                                atype=result.anomaly_type,
                                z=_format_number(result.z_score, 2),
                                mag=_format_percent(result.magnitude_pct, 2),
                            ),
                            "warning",
                        )

                snapshot = QuantSnapshot(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=datetime.now(timezone.utc),
                    candles=list(window_candles),
                    prices=prices,
                    open_interest=list(oi_points),
                    cvd=cvd_values,
                    cvd_deltas=cvd_deltas,
                    price_current=price_current,
                    oi_current=oi_current,
                    cvd_current=cvd_current,
                    funding_rate=funding_rate,
                    order_book=depth_metrics,
                    vwap=vwap_metrics,
                    atr=atr_metrics,
                    netflow=netflow,
                    anomalies=anomalies,
                    price_slope=price_slope,
                    price_slope_z=price_slope_z,
                    oi_slope=oi_slope,
                    oi_slope_z=oi_slope_z,
                    cvd_slope=cvd_slope,
                    cvd_slope_z=cvd_slope_z,
                )

                self._cache.set(snapshot)
                snapshots.append(snapshot)
                await _raise_if_cancelled(cancel_check)
                await _emit_snapshot(snapshot_callback, snapshot)

                summary_parts: List[str] = []
                if price_current is not None:
                    summary_parts.append(f"Price ${price_current:,.2f}")
                if oi_current is not None:
                    summary_parts.append(f"OI ${oi_current:,.0f}")
                if cvd_deltas:
                    summary_parts.append(f"CVD Δ {cvd_deltas[-1]:+,.0f}")
                summary = " | ".join(summary_parts) if summary_parts else "Snapshot ready"
                await _emit_log(
                    log_callback,
                    f"  ✓ {symbol}: {summary}",
                    "success",
                )

        return snapshots

    def get_snapshot(self, symbol: str, timeframe: str) -> Optional[QuantSnapshot]:
        return self._cache.get(symbol, timeframe)

    def get_all_snapshots(self) -> List[QuantSnapshot]:
        return self._cache.all()

    def clear_cache(self) -> None:
        self._cache.clear()

    def clear_symbol(self, symbol: str) -> None:
        self._cache.clear_symbol(symbol)


def _normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def _normalize_asset(asset: str, quote_asset: str) -> str:
    value = asset.strip().upper()
    if not value:
        return ""
    if "/" in value or ":" in value:
        return value
    return f"{value}/{quote_asset}"


def _timeframe_minutes(timeframe: str) -> Optional[int]:
    if not timeframe:
        return None
    value = timeframe.strip().lower()
    if value.endswith("m") and value[:-1].isdigit():
        return int(value[:-1])
    if value.endswith("h") and value[:-1].isdigit():
        return int(value[:-1]) * 60
    if value.endswith("d") and value[:-1].isdigit():
        return int(value[:-1]) * 1440
    return None
