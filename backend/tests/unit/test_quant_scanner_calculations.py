from app.domain.portfolio.models import MarketCandle
from app.domain.quant_scanner.calculations import calculate_cvd_from_candles


def test_calculate_cvd_from_candles():
    candles = [
        MarketCandle(timestamp_ms=1, open=1, high=2, low=1, close=2, volume=10),
        MarketCandle(timestamp_ms=2, open=2, high=2, low=1, close=1, volume=10),
    ]
    cvd_values, deltas = calculate_cvd_from_candles(candles)

    assert deltas == [10.0, -10.0]
    assert cvd_values == [10.0, 0.0]
