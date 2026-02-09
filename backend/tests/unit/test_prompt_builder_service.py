from datetime import datetime, timezone

import pytest

from app.application.prompt_builder.service import PromptBuilderService, PromptBuildError
from app.domain.prompt_builder.models import ChartRequest, PromptBuildRequest, PromptTemplate
from app.domain.quant_scanner.models import QuantSnapshot
from app.domain.portfolio.models import MarketCandle, MarketDataPoint, FundingRateSnapshot


class StubTemplateRepo:
    def __init__(self, template: PromptTemplate) -> None:
        self._template = template

    async def get_by_id(self, template_id: int):
        if template_id == self._template.id:
            return self._template
        return None

    async def get_default(self):
        return self._template


class StubQuantProvider:
    def __init__(self, snapshot: QuantSnapshot) -> None:
        self._snapshot = snapshot

    def get_snapshot(self, symbol: str, timeframe: str):
        if symbol == self._snapshot.symbol and timeframe == self._snapshot.timeframe:
            return self._snapshot
        return None


class StubChartGenerator:
    def render_with_overlays(self, symbol, interval, candle_limit, overlays=None):  # noqa: ANN001
        return b"fakeimage"


class StubChartGeneratorMissing:
    def render_with_overlays(self, symbol, interval, candle_limit, overlays=None):  # noqa: ANN001
        return None


class StubPortfolioState:
    account_value = 1000.0
    total_margin_used = 0.0


class StubPortfolioSnapshot:
    state = StubPortfolioState()
    positions = []


class StubDailyPnl:
    realized_pnl = 0.0
    trade_count = 0


class StubPortfolioService:
    async def get_portfolio_snapshot(self):
        return StubPortfolioSnapshot()

    async def get_daily_pnl(self):
        return StubDailyPnl()

    async def get_open_orders(self):
        return []

    async def get_recent_trades(self, limit):  # noqa: ANN001
        return []


class StubRiskConfig:
    exposure_pct = 20.0
    final_goal_usd = 0.0
    goal_deadline = None


class StubRiskConfigService:
    async def get_config(self):
        return StubRiskConfig()


class StubUploader:
    async def upload(self, image_bytes: bytes, name: str):
        if not image_bytes:
            return None
        return f"local://{name}.png"

    async def close(self):
        return None


class StubUploaderService:
    def __init__(self, uploader: StubUploader) -> None:
        self._uploader = uploader

    async def get_uploader(self):
        return self._uploader


def _build_snapshot() -> QuantSnapshot:
    candle = MarketCandle(
        timestamp_ms=1700000000000,
        open=1.0,
        high=1.2,
        low=0.9,
        close=1.1,
        volume=10.0,
    )
    oi_point = MarketDataPoint(timestamp_ms=1700000000000, value=100.0)
    funding = FundingRateSnapshot(rate=0.0001, timestamp_ms=1700000000000)
    return QuantSnapshot(
        symbol="BTC",
        timeframe="2h",
        timestamp=datetime(2024, 9, 1, tzinfo=timezone.utc),
        candles=[candle],
        prices=[1.1],
        open_interest=[oi_point],
        cvd=[0.5],
        cvd_deltas=[0.5],
        price_current=1.1,
        oi_current=100.0,
        cvd_current=0.5,
        funding_rate=funding,
    )


@pytest.mark.asyncio
async def test_prompt_builder_builds_prompt_with_filtered_fields():
    template = PromptTemplate(
        id=1,
        name="default",
        intro="Hello {ticker}",
        response_format="OK",
        quant_fields=["price_current", "funding_rate"],
        chart_defaults={"candles": 50, "overlays": ["ema"]},
        is_default=True,
    )
    snapshot = _build_snapshot()

    service = PromptBuilderService(
        template_repository=StubTemplateRepo(template),
        quant_provider=StubQuantProvider(snapshot),
        chart_preview_service=StubChartGenerator(),
        uploader_service=StubUploaderService(StubUploader()),
        portfolio_service=StubPortfolioService(),
        risk_config_service=StubRiskConfigService(),
    )

    request = PromptBuildRequest(
        request_id="req-1",
        template_id=1,
        trigger_reason="new_resonance",
        tickers=["BTC"],
        intervals=["2h"],
        chart_requests=[ChartRequest(interval="2h", candles=50, overlays=["ema"])],
        template_context={"ticker": "BTC"},
    )

    result = await service.build(request)
    assert "Hello BTC" in result.prompt_text
    assert result.data["quant_data"]["BTC"]["2h"]["price_current"] == 1.1
    assert "funding_rate" in result.data["quant_data"]["BTC"]["2h"]
    assert result.chart_items


@pytest.mark.asyncio
async def test_prompt_builder_raises_on_missing_snapshot():
    template = PromptTemplate(
        id=1,
        name="default",
        intro="Hello",
        response_format="OK",
        quant_fields=["price_current"],
        is_default=True,
    )
    snapshot = _build_snapshot()
    service = PromptBuilderService(
        template_repository=StubTemplateRepo(template),
        quant_provider=StubQuantProvider(snapshot),
        chart_preview_service=StubChartGenerator(),
        uploader_service=StubUploaderService(StubUploader()),
        portfolio_service=StubPortfolioService(),
        risk_config_service=StubRiskConfigService(),
    )

    request = PromptBuildRequest(
        request_id="req-2",
        template_id=1,
        trigger_reason="new_resonance",
        tickers=["ETH"],
        intervals=["2h"],
    )

    with pytest.raises(PromptBuildError):
        await service.build(request)


@pytest.mark.asyncio
async def test_prompt_builder_raises_on_missing_charts():
    template = PromptTemplate(
        id=1,
        name="default",
        intro="Hello",
        response_format="OK",
        quant_fields=["price_current"],
        is_default=True,
    )
    snapshot = _build_snapshot()
    service = PromptBuilderService(
        template_repository=StubTemplateRepo(template),
        quant_provider=StubQuantProvider(snapshot),
        chart_preview_service=StubChartGeneratorMissing(),
        uploader_service=StubUploaderService(StubUploader()),
        portfolio_service=StubPortfolioService(),
        risk_config_service=StubRiskConfigService(),
    )

    request = PromptBuildRequest(
        request_id="req-3",
        template_id=1,
        trigger_reason="new_resonance",
        tickers=["BTC"],
        intervals=["2h"],
        chart_requests=[ChartRequest(interval="2h")],
        template_context={"ticker": "BTC"},
    )

    with pytest.raises(PromptBuildError) as exc:
        await service.build(request)
    assert "missing chart snapshots" in str(exc.value).lower()
