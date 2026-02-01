import math

import pytest

from app.domain.portfolio.models import MarketCandle, OrderBookLevel, OrderBookSnapshot
from app.domain.quant_scanner.calculations import (
    calculate_depth_metrics,
    calculate_vwap_metrics,
    calculate_atr_metrics,
    calculate_slope_with_zscore,
    analyze_anomalies,
)
from app.domain.quant_scanner.models import NetflowMetrics


def test_calculate_depth_metrics_filters_by_range():
    snapshot = OrderBookSnapshot(
        symbol="BTC/USDT",
        timestamp_ms=1,
        bids=[
            OrderBookLevel(price=100.0, size=1.0),
            OrderBookLevel(price=99.5, size=2.0),
            OrderBookLevel(price=98.0, size=3.0),
        ],
        asks=[
            OrderBookLevel(price=100.5, size=1.0),
            OrderBookLevel(price=101.0, size=2.0),
            OrderBookLevel(price=102.0, size=3.0),
        ],
    )

    metrics = calculate_depth_metrics(snapshot, range_pct=0.5)

    assert metrics is not None
    assert metrics.bid_volume_usd == pytest.approx(100.0)
    assert metrics.ask_volume_usd == pytest.approx(100.5)
    assert metrics.net_depth_usd == pytest.approx(-0.5)
    assert metrics.imbalance_pct == pytest.approx(-0.249376, rel=1e-4)
    assert metrics.obi_ratio == pytest.approx(100.0 / 100.5)
    assert metrics.best_bid == pytest.approx(100.0)
    assert metrics.best_ask == pytest.approx(100.5)


def test_calculate_vwap_metrics():
    candles = [
        MarketCandle(timestamp_ms=1, open=100, high=110, low=90, close=100, volume=10),
        MarketCandle(timestamp_ms=2, open=110, high=120, low=100, close=110, volume=20),
        MarketCandle(timestamp_ms=3, open=120, high=130, low=110, close=120, volume=30),
    ]

    metrics = calculate_vwap_metrics(candles, price_current=120)

    assert metrics is not None
    assert metrics.value == pytest.approx(113.3333333333, rel=1e-6)
    assert metrics.std_dev == pytest.approx(7.453559925, rel=1e-6)
    assert metrics.distance == pytest.approx(0.89442719, rel=1e-6)
    assert metrics.candle_count == 3


def test_calculate_atr_metrics_basic():
    candles = [
        MarketCandle(timestamp_ms=1, open=100, high=110, low=100, close=105, volume=1),
        MarketCandle(timestamp_ms=2, open=105, high=115, low=105, close=110, volume=1),
        MarketCandle(timestamp_ms=3, open=110, high=120, low=110, close=115, volume=1),
        MarketCandle(timestamp_ms=4, open=115, high=125, low=115, close=120, volume=1),
        MarketCandle(timestamp_ms=5, open=120, high=130, low=120, close=125, volume=1),
    ]

    metrics = calculate_atr_metrics(candles, period=3, lookback=4, slope_window=2)

    assert metrics is not None
    assert metrics.value == pytest.approx(10.0)
    assert metrics.slope_pct == pytest.approx(0.0)
    assert metrics.z_score is None
    assert metrics.period == 3
    assert metrics.lookback == 2


def test_calculate_slope_with_zscore():
    values = [100, 101, 102, 103, 104, 105, 106, 107, 108]
    slope, z_score = calculate_slope_with_zscore(values, window_size=3)

    assert slope > 0
    assert z_score is not None
    assert math.isfinite(z_score)


def test_analyze_anomalies_spike_and_dip():
    prices = [100, 100, 100, 100, 100, 200]
    open_interest = [10, 10, 10, 10, 10, 10]
    cvd_values = [0, 0, 0, 0, 0, -100]

    anomalies = analyze_anomalies(
        prices,
        open_interest,
        cvd_values,
        window_size=6,
    )

    assert anomalies.price.anomaly_type == "spike"
    assert math.isinf(anomalies.price.z_score)
    assert anomalies.price.is_significant

    assert anomalies.open_interest.anomaly_type == "normal"
    assert anomalies.open_interest.is_significant is False

    assert anomalies.cvd.anomaly_type == "dip"
    assert math.isinf(anomalies.cvd.z_score)
    assert anomalies.cvd.is_significant


def test_netflow_metrics_from_api_response():
    raw = {
        "data": {
            "netflow": {
                "institution": {"future": {"1h": 1_500_000}},
                "personal": {"future": {"1h": -200_000}},
            }
        }
    }

    metrics = NetflowMetrics.from_api_response(raw, "1h")

    assert metrics is not None
    assert metrics.institution_netflow == pytest.approx(1_500_000)
    assert metrics.retail_netflow == pytest.approx(-200_000)
    assert metrics.total_netflow == pytest.approx(1_300_000)
    assert metrics.flow_regime == "strong_inflow"
    assert metrics.dominant_flow == "institution"
    assert metrics.timeframe == "1h"
