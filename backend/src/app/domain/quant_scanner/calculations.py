from __future__ import annotations

import math
import statistics
from typing import List, Tuple, Optional

from app.domain.portfolio.models import MarketCandle, OrderBookSnapshot
from app.domain.quant_scanner.models import DepthMetrics, VwapMetrics, AtrMetrics, AnomalyResult, AnomalySnapshot


def calculate_cvd_from_candles(candles: List[MarketCandle]) -> Tuple[List[float], List[float]]:
    cvd_values: List[float] = []
    deltas: List[float] = []
    cumulative = 0.0

    for candle in candles:
        high_low = candle.high - candle.low
        if high_low <= 0:
            delta = 0.0
        else:
            close_open = candle.close - candle.open
            buy_ratio = (close_open / high_low + 1) / 2
            buy_ratio = min(max(buy_ratio, 0.0), 1.0)
            delta = candle.volume * (2 * buy_ratio - 1)

        deltas.append(delta)
        cumulative += delta
        cvd_values.append(cumulative)

    return cvd_values, deltas


def calculate_depth_metrics(
    order_book: OrderBookSnapshot,
    range_pct: float = 0.5,
) -> Optional[DepthMetrics]:
    if not order_book.bids or not order_book.asks:
        return None

    best_bid = order_book.bids[0].price
    best_ask = order_book.asks[0].price
    if best_bid <= 0 or best_ask <= 0:
        return None

    mid_price = (best_bid + best_ask) / 2
    if mid_price <= 0:
        return None

    range_factor = range_pct / 100
    lower_bound = mid_price * (1 - range_factor)
    upper_bound = mid_price * (1 + range_factor)

    bid_volume_usd = 0.0
    for level in order_book.bids:
        if level.price >= lower_bound:
            bid_volume_usd += level.price * level.size
        else:
            break

    ask_volume_usd = 0.0
    for level in order_book.asks:
        if level.price <= upper_bound:
            ask_volume_usd += level.price * level.size
        else:
            break

    net_depth_usd = bid_volume_usd - ask_volume_usd
    total_volume = bid_volume_usd + ask_volume_usd
    imbalance_pct = (net_depth_usd / total_volume * 100) if total_volume > 0 else 0.0
    obi_ratio = (bid_volume_usd / ask_volume_usd) if ask_volume_usd > 0 else None

    return DepthMetrics(
        bid_volume_usd=bid_volume_usd,
        ask_volume_usd=ask_volume_usd,
        net_depth_usd=net_depth_usd,
        imbalance_pct=imbalance_pct,
        obi_ratio=obi_ratio,
        mid_price=mid_price,
        range_pct=range_pct,
        best_bid=best_bid,
        best_ask=best_ask,
    )


def calculate_vwap_metrics(
    candles: List[MarketCandle],
    price_current: Optional[float] = None,
) -> Optional[VwapMetrics]:
    if len(candles) < 3:
        return None

    total_volume = 0.0
    weighted_sum = 0.0
    typical_prices: List[float] = []
    volumes: List[float] = []

    for candle in candles:
        if candle.volume <= 0:
            continue
        typical = (candle.high + candle.low + candle.close) / 3.0
        typical_prices.append(typical)
        volumes.append(candle.volume)
        total_volume += candle.volume
        weighted_sum += typical * candle.volume

    if total_volume <= 0 or not typical_prices:
        return None

    vwap = weighted_sum / total_volume
    variance = 0.0
    for typical, volume in zip(typical_prices, volumes):
        variance += volume * (typical - vwap) ** 2
    variance = variance / total_volume
    std_dev = math.sqrt(variance)

    current_price = price_current if price_current is not None else candles[-1].close
    distance = (current_price - vwap) / std_dev if std_dev > 0 else 0.0

    return VwapMetrics(
        value=vwap,
        std_dev=std_dev,
        distance=distance,
        candle_count=len(typical_prices),
    )


def calculate_atr_metrics(
    candles: List[MarketCandle],
    period: int = 14,
    lookback: int = 100,
    slope_window: int = 5,
) -> Optional[AtrMetrics]:
    if period < 1 or slope_window < 2:
        return None
    if len(candles) < period + 1:
        return None

    true_ranges: List[float] = []
    for idx in range(1, len(candles)):
        current = candles[idx]
        previous = candles[idx - 1]
        high_low = current.high - current.low
        high_close = abs(current.high - previous.close)
        low_close = abs(current.low - previous.close)
        true_ranges.append(max(high_low, high_close, low_close))

    if len(true_ranges) < period:
        return None

    atr_series: List[float] = []
    first_atr = sum(true_ranges[:period]) / period
    atr_series.append(first_atr)
    for tr in true_ranges[period:]:
        prev_atr = atr_series[-1]
        atr_series.append(((period - 1) * prev_atr + tr) / period)

    if not atr_series:
        return None

    current_atr = atr_series[-1]
    slope_window = min(slope_window, len(atr_series))
    atr_slope = _compute_pct_slope(atr_series[-slope_window:])

    lookback = min(lookback, len(atr_series))
    history = atr_series[-lookback:]
    atr_z = _z_score(history) if len(history) >= 5 else None

    return AtrMetrics(
        value=current_atr,
        slope_pct=atr_slope,
        z_score=atr_z,
        period=period,
        lookback=lookback,
    )


def calculate_normalized_slope(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0

    start_val = values[0]
    if start_val == 0:
        return 0.0

    y_normalized: List[float] = []
    for value in values:
        pct_change = ((value - start_val) / abs(start_val)) * 100
        y_normalized.append(pct_change)

    x = list(range(len(y_normalized)))
    n = len(x)
    sum_x = sum(x)
    sum_y = sum(y_normalized)
    sum_xy = sum(x[i] * y_normalized[i] for i in range(n))
    sum_x_squared = sum(xi * xi for xi in x)

    denominator = n * sum_x_squared - sum_x * sum_x
    if denominator == 0:
        return 0.0

    return (n * sum_xy - sum_x * sum_y) / denominator


def calculate_slope_with_zscore(
    values: List[float],
    window_size: int = 6,
) -> Tuple[float, Optional[float]]:
    if len(values) < window_size:
        return 0.0, None

    historical_slopes: List[float] = []
    for idx in range(len(values) - window_size + 1):
        window = values[idx:idx + window_size]
        historical_slopes.append(calculate_normalized_slope(window))

    if not historical_slopes:
        return 0.0, None

    current_slope = historical_slopes[-1]
    if len(historical_slopes) < 5:
        return current_slope, None

    mean_slope = statistics.mean(historical_slopes)
    std_slope = statistics.stdev(historical_slopes) if len(historical_slopes) > 1 else 0.0
    if std_slope == 0:
        return current_slope, 0.0

    return current_slope, (current_slope - mean_slope) / std_slope


def analyze_anomalies(
    prices: List[float],
    open_interest: List[float],
    cvd_values: List[float],
    window_size: int = 20,
) -> AnomalySnapshot:
    price_result = _analyze_anomaly_factor(prices, "price", threshold=2.5, window_size=window_size)
    oi_result = _analyze_anomaly_factor(open_interest, "oi", threshold=2.0, window_size=window_size)
    cvd_result = _analyze_anomaly_factor(cvd_values, "cvd", threshold=2.0, window_size=window_size)
    return AnomalySnapshot(
        price=price_result,
        open_interest=oi_result,
        cvd=cvd_result,
    )


def _analyze_anomaly_factor(
    values: List[float],
    factor: str,
    threshold: float,
    window_size: int,
    min_points: int = 5,
) -> AnomalyResult:
    clean_values = [value for value in values if value is not None]
    if len(clean_values) < min_points:
        return AnomalyResult(
            factor=factor,
            anomaly_type="normal",
            z_score=0.0,
            magnitude_pct=0.0,
            baseline_mean=0.0,
            baseline_std=0.0,
            threshold=threshold,
            is_significant=False,
            current_value=clean_values[-1] if clean_values else 0.0,
            insufficient_data=True,
        )

    window = clean_values[-window_size:] if len(clean_values) >= window_size else clean_values
    baseline = window[:-1]
    current = window[-1]
    if not baseline:
        return AnomalyResult(
            factor=factor,
            anomaly_type="normal",
            z_score=0.0,
            magnitude_pct=0.0,
            baseline_mean=current,
            baseline_std=0.0,
            threshold=threshold,
            is_significant=False,
            current_value=current,
            insufficient_data=True,
        )

    mean = sum(baseline) / len(baseline)
    if len(baseline) < 2:
        std_dev = 0.0
    else:
        variance = sum((value - mean) ** 2 for value in baseline) / len(baseline)
        std_dev = math.sqrt(variance)

    if std_dev == 0:
        if current == mean:
            z_score = 0.0
        else:
            z_score = float("inf") if current > mean else float("-inf")
    else:
        z_score = (current - mean) / std_dev

    if mean != 0:
        magnitude_pct = ((current - mean) / abs(mean)) * 100
    else:
        magnitude_pct = 0.0 if current == 0 else (float("inf") if current > 0 else float("-inf"))

    anomaly_type = "normal"
    if z_score > threshold:
        anomaly_type = "spike"
    elif z_score < -threshold:
        anomaly_type = "dip"

    return AnomalyResult(
        factor=factor,
        anomaly_type=anomaly_type,
        z_score=z_score,
        magnitude_pct=magnitude_pct,
        baseline_mean=mean,
        baseline_std=std_dev,
        threshold=threshold,
        is_significant=abs(z_score) > threshold,
        current_value=current,
        insufficient_data=False,
    )


def _compute_pct_slope(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    first = values[0]
    last = values[-1]
    if first == 0:
        return 0.0
    total_change_pct = ((last - first) / first) * 100
    return total_change_pct / (len(values) - 1)


def _z_score(values: List[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    mean = statistics.mean(values)
    std_dev = statistics.pstdev(values)
    if std_dev == 0:
        return 0.0
    return (values[-1] - mean) / std_dev
