from datetime import datetime, timezone

import pytest

from app.application.prompt_builder.service import PromptBuilderService, PromptBuildError
from app.domain.chart_generator.models import AtrOverlay
from app.domain.prompt_builder.models import ChartRequest, PromptBuildRequest, PromptTemplate
from app.domain.quant_scanner.models import QuantSnapshot
from app.domain.portfolio.models import FundingRateSnapshot, MarketCandle, MarketDataPoint, Position
from app.infrastructure.external.codex_temp_images import CodexTempImageStore


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
    def __init__(self) -> None:
        self.calls = []

    def render_with_overlays(self, symbol, interval, candle_limit, overlays=None):  # noqa: ANN001
        self.calls.append(
            {
                "symbol": symbol,
                "interval": interval,
                "candle_limit": candle_limit,
                "overlays": list(overlays or []),
            }
        )
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


class StubPortfolioSnapshotWithPosition:
    state = StubPortfolioState()

    def __init__(self) -> None:
        self.positions = [
            Position(
                symbol="TON/USDT",
                direction="long",
                size=10.0,
                entry_price=3.25,
                mark_price=3.41,
                unrealized_pnl=1.75,
                liquidation_price=2.1,
                margin=5.0,
                leverage=6.0,
                opened_at=datetime(2024, 9, 1, 10, 0, tzinfo=timezone.utc),
            )
        ]


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


class StubPortfolioServiceWithPosition(StubPortfolioService):
    async def get_portfolio_snapshot(self):
        return StubPortfolioSnapshotWithPosition()


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


def _build_snapshot(symbol: str = "BTC") -> QuantSnapshot:
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
        symbol=symbol,
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
    assert isinstance(result.data["quant_data"], list)
    row = result.data["quant_data"][0]
    assert row["ticker"] == "BTC"
    assert row["interval"] == "2h"
    assert row["price_current"] == "$1.10"
    assert "funding_rate" in row
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


@pytest.mark.asyncio
async def test_prompt_builder_includes_atr_overlay_by_default():
    template = PromptTemplate(
        id=1,
        name="default",
        intro="Hello",
        response_format="OK",
        quant_fields=["price_current"],
        chart_defaults={"candles": 50},
        is_default=True,
    )
    snapshot = _build_snapshot()
    chart_preview = StubChartGenerator()
    service = PromptBuilderService(
        template_repository=StubTemplateRepo(template),
        quant_provider=StubQuantProvider(snapshot),
        chart_preview_service=chart_preview,
        uploader_service=StubUploaderService(StubUploader()),
        portfolio_service=StubPortfolioService(),
        risk_config_service=StubRiskConfigService(),
    )

    request = PromptBuildRequest(
        request_id="req-atr",
        template_id=1,
        trigger_reason="new_resonance",
        tickers=["BTC"],
        intervals=["2h"],
        chart_requests=[ChartRequest(interval="2h", candles=50)],
    )

    await service.build(request)
    assert chart_preview.calls
    overlays = chart_preview.calls[0]["overlays"]
    assert any(isinstance(item, AtrOverlay) and item.length == 14 for item in overlays)


@pytest.mark.asyncio
async def test_prompt_builder_uses_local_codex_temp_images(tmp_path):
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
        codex_temp_images=CodexTempImageStore(tmp_path),
    )

    request = PromptBuildRequest(
        request_id="req-codex",
        template_id=1,
        trigger_reason="new_resonance",
        tickers=["BTC"],
        intervals=["2h"],
        provider="codex",
        chart_requests=[ChartRequest(interval="2h")],
    )

    result = await service.build(request)
    assert result.chart_items
    image_url = result.chart_items[0]["image_url"]
    assert image_url.startswith(str(tmp_path))


@pytest.mark.asyncio
async def test_prompt_builder_formats_position_management_template_context():
    template = PromptTemplate(
        id=1,
        name="pm",
        intro=(
            "You have an open {direction} position on {ticker}. "
            "Entry: ${entry_price} | Current: {current_price} | "
            "Unrealized PnL: {pnl_display} | Duration: {duration}"
        ),
        response_format="OK",
        quant_fields=["price_current"],
        chart_defaults={"data_selections": ["quantitative_signals"]},
        is_default=True,
    )
    snapshot = _build_snapshot("TON/USDT")
    service = PromptBuilderService(
        template_repository=StubTemplateRepo(template),
        quant_provider=StubQuantProvider(snapshot),
        chart_preview_service=StubChartGenerator(),
        uploader_service=StubUploaderService(StubUploader()),
        portfolio_service=StubPortfolioServiceWithPosition(),
        risk_config_service=StubRiskConfigService(),
    )

    request = PromptBuildRequest(
        request_id="req-pm",
        template_id=1,
        trigger_reason="position_management",
        tickers=["TON/USDT"],
        intervals=["2h"],
        template_context={"ticker": "TON/USDT"},
    )

    result = await service.build(request)

    assert "open LONG position on TON/USDT" in result.prompt_text
    assert "Entry: $3.2500" in result.prompt_text
    assert "Current: $3.4100" in result.prompt_text
    assert "Unrealized PnL: $1.75" in result.prompt_text
    assert "Duration: " in result.prompt_text
