import pytest

pytest.importorskip("pandas")
pytest.importorskip("mplfinance")
pytest.importorskip("matplotlib")

from app.application.chart_generator import ChartGenerator
from app.domain.chart_generator import (
    AtrOverlay,
    ChartData,
    ChartRenderRequest,
    EmaOverlay,
    VwapOverlay,
    BollingerBandsOverlay,
)
from app.domain.portfolio.models import MarketCandle


def test_chart_generator_renders_png():
    candles = []
    for idx in range(30):
        base = 100 + idx
        candles.append(
            MarketCandle(
                timestamp_ms=1_700_000_000_000 + idx * 60_000,
                open=base,
                high=base + 2,
                low=base - 2,
                close=base + 1,
                volume=100 + idx,
            )
        )

    request = ChartRenderRequest(
        data=ChartData(symbol="BTC/USDT", timeframe="1m", candles=candles),
        overlays=[
            EmaOverlay(length=10),
            EmaOverlay(length=20, color="#FF9800"),
            VwapOverlay(),
            BollingerBandsOverlay(),
            AtrOverlay(length=14),
        ],
        candle_limit=25,
    )

    image_bytes = ChartGenerator().render(request)

    assert image_bytes is not None
    assert len(image_bytes) > 1000


def test_chart_generator_handles_empty_input():
    request = ChartRenderRequest(
        data=ChartData(symbol="BTC/USDT", timeframe="1m", candles=[]),
        overlays=[],
    )

    assert ChartGenerator().render(request) is None
