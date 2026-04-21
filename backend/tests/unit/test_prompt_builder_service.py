from datetime import datetime, timezone

import pytest

from app.application.prompt_builder.service import PromptBuilderService, PromptBuildError
from app.domain.auto_add.models import (
    AutoAddPositionRecord,
    AutoAddPositionSnapshot,
    AutoAddStatus,
    AutoAddTrancheKind,
    AutoAddTrancheRecord,
    AutoAddTrancheStatus,
)
from app.domain.chart_generator.models import AtrOverlay
from app.domain.position_origin.models import ActivePositionOriginRecord
from app.domain.position_origin.symbols import normalize_position_origin_symbol
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
    account = type("Account", (), {"id": "acc-1"})()
    state = StubPortfolioState()
    positions = []


class StubPortfolioSnapshotWithPosition:
    account = type("Account", (), {"id": "acc-1"})()
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


class StubPortfolioSnapshotWithPositionNoOpenedAt:
    account = type("Account", (), {"id": "acc-1"})()
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
                opened_at=None,
            )
        ]


class StubPortfolioSnapshotWithLowPricePosition:
    account = type("Account", (), {"id": "acc-1"})()
    state = StubPortfolioState()

    def __init__(self) -> None:
        self.positions = [
            Position(
                symbol="ACH/USDT",
                direction="long",
                size=1000.0,
                entry_price=0.005973,
                mark_price=0.006053,
                unrealized_pnl=0.08,
                liquidation_price=0.003018,
                margin=3.0,
                leverage=2.0,
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

    async def get_recent_completed_trades(self, limit):  # noqa: ANN001
        del limit
        return []


class StubPortfolioServiceWithPosition(StubPortfolioService):
    async def get_portfolio_snapshot(self):
        return StubPortfolioSnapshotWithPosition()


class StubPortfolioServiceWithPositionNoOpenedAt(StubPortfolioService):
    async def get_portfolio_snapshot(self):
        return StubPortfolioSnapshotWithPositionNoOpenedAt()


class StubPortfolioServiceWithLowPricePosition(StubPortfolioService):
    async def get_portfolio_snapshot(self):
        return StubPortfolioSnapshotWithLowPricePosition()


class StubPortfolioServiceWithPositionAndTpOrder(StubPortfolioServiceWithPosition):
    async def get_open_orders(self):
        return [
            {
                "symbol": "TON/USDT",
                "type": "TAKE_PROFIT_MARKET",
                "stopPrice": 3.5,
                "status": "NEW",
            }
        ]


class StubPortfolioServiceWithPositionAndNestedProtectionOrders(StubPortfolioServiceWithPosition):
    async def get_open_orders(self):
        return [
            {
                "symbol": "TONUSDT",
                "status": "NEW",
                "info": {
                    "symbol": "TONUSDT",
                    "orderType": "STOP_MARKET",
                    "triggerPrice": "3.10",
                },
            },
            {
                "symbol": "TONUSDT",
                "status": "NEW",
                "info": {
                    "symbol": "TONUSDT",
                    "orderType": "TAKE_PROFIT_MARKET",
                    "triggerPrice": "3.50",
                },
            },
        ]


class StubPortfolioServiceWithLowPriceProtectionOrders(StubPortfolioServiceWithLowPricePosition):
    async def get_open_orders(self):
        return [
            {
                "symbol": "ACHUSDT",
                "status": "NEW",
                "info": {
                    "symbol": "ACHUSDT",
                    "orderType": "STOP_MARKET",
                    "triggerPrice": "0.005915",
                },
            },
            {
                "symbol": "ACHUSDT",
                "status": "NEW",
                "info": {
                    "symbol": "ACHUSDT",
                    "orderType": "TAKE_PROFIT_MARKET",
                    "triggerPrice": "0.006129",
                },
            },
        ]


class StubPortfolioServiceWithCompletedTrades(StubPortfolioService):
    async def get_recent_completed_trades(self, limit):  # noqa: ANN001
        assert limit == 10
        return [
            {
                "symbol": "BTC",
                "direction": "long",
                "entry_price": 100000,
                "exit_price": 101500,
                "pnl": 15.0,
                "roi_pct": 1.5,
                "entry_time": 1700000000000,
                "exit_time": 1700003600000,
                "duration_minutes": 60,
            }
        ]


class StubRiskConfig:
    exposure_pct = 20.0
    final_goal_usd = 0.0
    goal_deadline = None


class StubRiskConfigService:
    async def get_config(self):
        return StubRiskConfig()


class StubPositionOriginService:
    def __init__(self, rows: dict[str, ActivePositionOriginRecord] | None = None) -> None:
        self._rows = rows or {}
        self.prune_calls: list[tuple[str, list[str]]] = []
        self.sync_calls: list[tuple[str, list[str]]] = []

    async def prune_missing(self, account_id: str, live_symbols):  # noqa: ANN001
        self.prune_calls.append((account_id, list(live_symbols)))
        return 0

    async def sync_live_positions(self, account_id: str, positions):  # noqa: ANN001
        self.sync_calls.append((account_id, [getattr(position, "symbol", None) for position in positions]))
        output = {}
        for position in positions:
            normalized = normalize_position_origin_symbol(getattr(position, "symbol", None))
            if not normalized:
                continue
            existing = self._rows.get(normalized)
            margin = getattr(position, "margin", None) or 0.0
            unrealized_pnl = getattr(position, "unrealized_pnl", None)
            current_roe = None
            if margin and unrealized_pnl is not None:
                current_roe = (unrealized_pnl / margin) * 100.0
            peak_roe = current_roe
            if existing is not None and existing.peak_roe is not None and current_roe is not None:
                peak_roe = max(existing.peak_roe, current_roe)
            record = ActivePositionOriginRecord(
                account_id=account_id,
                symbol=normalized,
                anchor_frame=existing.anchor_frame if existing is not None else None,
                active_tunnel=existing.active_tunnel if existing is not None else None,
                stop_loss_roe=existing.stop_loss_roe if existing is not None else None,
                take_profit_roe=existing.take_profit_roe if existing is not None else None,
                position_side=existing.position_side if existing is not None else getattr(position, "direction", None),
                exchange_opened_at=(
                    existing.exchange_opened_at
                    if existing is not None and existing.exchange_opened_at is not None
                    else getattr(position, "opened_at", None)
                ),
                peak_roe=peak_roe,
                created_at=existing.created_at if existing is not None else None,
            )
            self._rows[normalized] = record
            output[normalized] = record
        return output

    async def get_many(self, account_id: str, symbols):  # noqa: ANN001
        del account_id
        output = {}
        for symbol in symbols:
            normalized = normalize_position_origin_symbol(symbol)
            if normalized in self._rows:
                output[normalized] = self._rows[normalized]
        return output


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


class StubAutoAddRepository:
    def __init__(self, snapshots: dict[str, AutoAddPositionSnapshot] | None = None) -> None:
        self._snapshots = {
            normalize_position_origin_symbol(symbol): snapshot
            for symbol, snapshot in (snapshots or {}).items()
        }

    async def list_latest_positions_for_symbols(self, account_id: str, symbols):  # noqa: ANN001
        del account_id
        rows = []
        for symbol in symbols:
            snapshot = self._snapshots.get(normalize_position_origin_symbol(symbol))
            if snapshot is not None:
                rows.append(snapshot.record)
        return rows

    async def list_tranches(self, auto_add_position_id: str):
        for snapshot in self._snapshots.values():
            if snapshot.record.id == auto_add_position_id:
                return list(snapshot.tranches)
        return []


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


@pytest.mark.asyncio
async def test_prompt_builder_includes_persisted_position_origin_metadata():
    template = PromptTemplate(
        id=1,
        name="positions",
        intro="Hello",
        response_format="OK",
        quant_fields=["price_current"],
        chart_defaults={
            "data_selections": ["open_positions"],
            "field_selections": {
                "open_positions": ["anchor_frame", "active_tunnel"],
            },
        },
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
        position_origin_service=StubPositionOriginService(
            {
                "TON": ActivePositionOriginRecord(
                    account_id="acc-1",
                    symbol="TON",
                    anchor_frame="4h",
                    active_tunnel="fast",
                )
            }
        ),
    )

    request = PromptBuildRequest(
        request_id="req-open-origin",
        template_id=1,
        trigger_reason="position_management",
        tickers=["TON/USDT"],
        intervals=["2h"],
    )

    result = await service.build(request)

    positions = result.data["open_positions"]
    assert positions["TON/USDT"]["anchor_frame"] == "4h"
    assert positions["TON/USDT"]["active_tunnel"] == "fast"


@pytest.mark.asyncio
async def test_prompt_builder_fills_missing_position_management_fields_from_live_snapshot():
    template = PromptTemplate(
        id=1,
        name="pm-filtered",
        intro=(
            "You have an open {direction} position on {ticker}. "
            "Entry: ${entry_price} | Current: ${current_price} | "
            "Unrealized PnL: {pnl_display} | Duration: {duration}"
        ),
        response_format="OK",
        quant_fields=["price_current"],
        chart_defaults={
            "data_selections": ["open_positions"],
            "field_selections": {
                "open_positions": ["pnl", "held_for"],
            },
        },
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
        request_id="req-pm-filtered",
        template_id=1,
        trigger_reason="position_management",
        tickers=["TON/USDT"],
        intervals=["2h"],
        template_context={"ticker": "TON/USDT"},
    )

    result = await service.build(request)

    assert "Entry: $$3.2500" not in result.prompt_text
    assert "Entry: $$3.4100" not in result.prompt_text
    assert "Entry: $$0.00" not in result.prompt_text
    assert "Entry: $$" not in result.prompt_text
    assert "Entry: $3.2500" in result.prompt_text
    assert "Current: $3.4100" in result.prompt_text
    assert "${current_price}" not in result.prompt_text


@pytest.mark.asyncio
async def test_prompt_builder_includes_current_take_profit_roe_fields():
    template = PromptTemplate(
        id=1,
        name="positions",
        intro="Hello",
        response_format="OK",
        quant_fields=["price_current"],
        chart_defaults={
            "data_selections": ["open_positions"],
            "field_selections": {
                "open_positions": [
                    "take_profit",
                    "current_take_profit_roe_pct",
                    "remaining_take_profit_roe_pct",
                ],
            },
        },
        is_default=True,
    )
    snapshot = _build_snapshot("TON/USDT")
    service = PromptBuilderService(
        template_repository=StubTemplateRepo(template),
        quant_provider=StubQuantProvider(snapshot),
        chart_preview_service=StubChartGenerator(),
        uploader_service=StubUploaderService(StubUploader()),
        portfolio_service=StubPortfolioServiceWithPositionAndTpOrder(),
        risk_config_service=StubRiskConfigService(),
    )

    request = PromptBuildRequest(
        request_id="req-open-tp-roe",
        template_id=1,
        trigger_reason="position_management",
        tickers=["TON/USDT"],
        intervals=["2h"],
    )

    result = await service.build(request)

    position = result.data["open_positions"]["TON/USDT"]
    assert position["take_profit"] == 3.5
    assert position["current_take_profit_roe_pct"] == 46.15
    assert position["remaining_take_profit_roe_pct"] == 16.62


@pytest.mark.asyncio
async def test_prompt_builder_extracts_sl_tp_from_nested_binance_style_orders():
    template = PromptTemplate(
        id=1,
        name="positions",
        intro="Hello",
        response_format="OK",
        quant_fields=["price_current"],
        chart_defaults={
            "data_selections": ["open_positions"],
            "field_selections": {
                "open_positions": [
                    "stop_loss",
                    "take_profit",
                    "current_take_profit_roe_pct",
                    "remaining_take_profit_roe_pct",
                ],
            },
        },
        is_default=True,
    )
    snapshot = _build_snapshot("TON/USDT")
    service = PromptBuilderService(
        template_repository=StubTemplateRepo(template),
        quant_provider=StubQuantProvider(snapshot),
        chart_preview_service=StubChartGenerator(),
        uploader_service=StubUploaderService(StubUploader()),
        portfolio_service=StubPortfolioServiceWithPositionAndNestedProtectionOrders(),
        risk_config_service=StubRiskConfigService(),
    )

    request = PromptBuildRequest(
        request_id="req-open-nested-protection",
        template_id=1,
        trigger_reason="position_management",
        tickers=["TON/USDT"],
        intervals=["2h"],
    )

    result = await service.build(request)

    position = result.data["open_positions"]["TON/USDT"]
    assert position["stop_loss"] == 3.1
    assert position["take_profit"] == 3.5
    assert position["current_take_profit_roe_pct"] == 46.15
    assert position["remaining_take_profit_roe_pct"] == 16.62


@pytest.mark.asyncio
async def test_prompt_builder_includes_default_single_tranche_for_open_position():
    template = PromptTemplate(
        id=1,
        name="positions",
        intro="Hello",
        response_format="OK",
        quant_fields=["price_current"],
        chart_defaults={
            "data_selections": ["open_positions"],
            "field_selections": {
                "open_positions": [
                    "filled_tranche_count",
                    "total_tranches",
                    "tranches",
                ],
            },
        },
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
        request_id="req-open-default-tranche",
        template_id=1,
        trigger_reason="position_management",
        tickers=["TON/USDT"],
        intervals=["2h"],
    )

    result = await service.build(request)

    position = result.data["open_positions"]["TON/USDT"]
    assert position["filled_tranche_count"] == 1
    assert position["total_tranches"] == 1
    assert position["tranches"] == [
        {
            "tranche_index": 0,
            "kind": "INITIAL",
            "filled": True,
            "status": "FILLED",
        }
    ]


@pytest.mark.asyncio
async def test_prompt_builder_includes_auto_add_tranche_fill_state():
    template = PromptTemplate(
        id=1,
        name="positions",
        intro="Hello",
        response_format="OK",
        quant_fields=["price_current"],
        chart_defaults={
            "data_selections": ["open_positions"],
            "field_selections": {
                "open_positions": [
                    "filled_tranche_count",
                    "total_tranches",
                    "tranches",
                ],
            },
        },
        is_default=True,
    )
    snapshot = _build_snapshot("TON/USDT")
    auto_add_snapshot = AutoAddPositionSnapshot(
        record=AutoAddPositionRecord(
            id="auto-add-1",
            account_id="acc-1",
            session_id="session-1",
            symbol="TON",
            side="long",
            status=AutoAddStatus.ACTIVE,
            initial_margin_used=5.0,
            initial_stop_price=3.1,
            original_risk_usd=1.5,
            trigger_basis_price=3.25,
            next_trigger_price=3.75,
            initial_entry_price=3.25,
            initial_quantity=10.0,
            expected_quantity=10.0,
            leverage=6.0,
            add_count=1,
            max_tranches=3,
            trigger_atr_multiple=1.0,
            tranche_margin_pct=0.80,
            protected_stop_roe=0.002,
            active=True,
            created_at=datetime(2024, 9, 1, 10, 0, tzinfo=timezone.utc),
            updated_at=datetime(2024, 9, 1, 10, 0, tzinfo=timezone.utc),
        ),
        tranches=(
            AutoAddTrancheRecord(
                id="tr-0",
                auto_add_position_id="auto-add-1",
                tranche_index=0,
                kind=AutoAddTrancheKind.INITIAL,
                status=AutoAddTrancheStatus.INITIAL,
                exchange_order_id=None,
                trigger_price=None,
                fill_price=3.25,
                filled_quantity=10.0,
                margin_used=5.0,
                position_notional_usd=32.5,
                fill_time=datetime(2024, 9, 1, 10, 0, tzinfo=timezone.utc),
                atr_value=0.25,
                trigger_basis_price=3.25,
            ),
            AutoAddTrancheRecord(
                id="tr-1",
                auto_add_position_id="auto-add-1",
                tranche_index=1,
                kind=AutoAddTrancheKind.ADD,
                status=AutoAddTrancheStatus.RESOLVED,
                exchange_order_id="ex-1",
                trigger_price=3.5,
                fill_price=3.5,
                filled_quantity=8.0,
                margin_used=4.0,
                position_notional_usd=28.0,
                fill_time=datetime(2024, 9, 1, 10, 15, tzinfo=timezone.utc),
                atr_value=0.25,
                trigger_basis_price=3.25,
            ),
            AutoAddTrancheRecord(
                id="tr-2",
                auto_add_position_id="auto-add-1",
                tranche_index=2,
                kind=AutoAddTrancheKind.ADD,
                status=AutoAddTrancheStatus.PLACED,
                exchange_order_id="ex-2",
                trigger_price=3.75,
                fill_price=None,
                filled_quantity=None,
                margin_used=4.0,
                position_notional_usd=30.0,
                fill_time=None,
                atr_value=0.25,
                trigger_basis_price=3.25,
            ),
        ),
    )
    service = PromptBuilderService(
        template_repository=StubTemplateRepo(template),
        quant_provider=StubQuantProvider(snapshot),
        chart_preview_service=StubChartGenerator(),
        uploader_service=StubUploaderService(StubUploader()),
        portfolio_service=StubPortfolioServiceWithPosition(),
        risk_config_service=StubRiskConfigService(),
        auto_add_repository=StubAutoAddRepository({"TON": auto_add_snapshot}),
    )

    request = PromptBuildRequest(
        request_id="req-open-auto-add-tranches",
        template_id=1,
        trigger_reason="position_management",
        tickers=["TON/USDT"],
        intervals=["2h"],
    )

    result = await service.build(request)

    position = result.data["open_positions"]["TON/USDT"]
    assert position["filled_tranche_count"] == 2
    assert position["total_tranches"] == 4
    assert position["tranches"] == [
        {
            "tranche_index": 0,
            "kind": "INITIAL",
            "filled": True,
            "status": "FILLED",
        },
        {
            "tranche_index": 1,
            "kind": "ADD",
            "filled": True,
            "status": "FILLED",
        },
        {
            "tranche_index": 2,
            "kind": "ADD",
            "filled": False,
            "status": "PENDING",
        },
        {
            "tranche_index": 3,
            "kind": "ADD",
            "filled": False,
            "status": "PLANNED",
        },
    ]


@pytest.mark.asyncio
async def test_prompt_builder_preserves_small_price_precision_for_open_position_protection():
    template = PromptTemplate(
        id=1,
        name="positions",
        intro="Hello",
        response_format="OK",
        quant_fields=["price_current"],
        chart_defaults={
            "data_selections": ["open_positions"],
            "field_selections": {
                "open_positions": [
                    "entry_price",
                    "current_price",
                    "stop_loss",
                    "take_profit",
                    "liquidation",
                ],
            },
        },
        is_default=True,
    )
    snapshot = _build_snapshot("ACH/USDT")
    service = PromptBuilderService(
        template_repository=StubTemplateRepo(template),
        quant_provider=StubQuantProvider(snapshot),
        chart_preview_service=StubChartGenerator(),
        uploader_service=StubUploaderService(StubUploader()),
        portfolio_service=StubPortfolioServiceWithLowPricePosition(),
        risk_config_service=StubRiskConfigService(),
    )

    request = PromptBuildRequest(
        request_id="req-open-low-price",
        template_id=1,
        trigger_reason="position_management",
        tickers=["ACH/USDT"],
        intervals=["2h"],
    )

    result = await service.build(request)

    position = result.data["open_positions"]["ACH/USDT"]
    assert position["entry_price"] == 0.005973
    assert position["current_price"] == 0.006053
    assert position["liquidation"] == 0.003018

    service = PromptBuilderService(
        template_repository=StubTemplateRepo(template),
        quant_provider=StubQuantProvider(snapshot),
        chart_preview_service=StubChartGenerator(),
        uploader_service=StubUploaderService(StubUploader()),
        portfolio_service=StubPortfolioServiceWithLowPriceProtectionOrders(),
        risk_config_service=StubRiskConfigService(),
    )

    result = await service.build(request)

    position = result.data["open_positions"]["ACH/USDT"]
    assert position["stop_loss"] == 0.005915
    assert position["take_profit"] == 0.006129


@pytest.mark.asyncio
async def test_prompt_builder_fills_signal_frame_and_active_tunnel_in_rich_text():
    template = PromptTemplate(
        id=1,
        name="pm-origin-rich-text",
        intro=(
            "Original signal frame: {signal_frame} | "
            "Active tunnel at entry: {active_tunnel}"
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
        position_origin_service=StubPositionOriginService(
            {
                "TON": ActivePositionOriginRecord(
                    account_id="acc-1",
                    symbol="TON",
                    anchor_frame="4h",
                    active_tunnel="fast",
                )
            }
        ),
    )

    request = PromptBuildRequest(
        request_id="req-pm-origin-rich-text",
        template_id=1,
        trigger_reason="position_management",
        tickers=["TON/USDT"],
        intervals=["2h"],
        template_context={"ticker": "TON/USDT"},
    )

    result = await service.build(request)

    assert "Original signal frame: 4h" in result.prompt_text
    assert "Active tunnel at entry: fast" in result.prompt_text


@pytest.mark.asyncio
async def test_prompt_builder_fills_peak_roe_in_position_management_rich_text():
    template = PromptTemplate(
        id=1,
        name="pm-peak-roe",
        intro="Peak ROE: {peak_roe}",
        response_format="OK",
        quant_fields=["price_current"],
        chart_defaults={
            "data_selections": ["open_positions"],
            "field_selections": {
                "open_positions": ["peak_roe"],
            },
        },
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
        request_id="req-pm-peak-roe",
        template_id=1,
        trigger_reason="position_management",
        tickers=["TON/USDT"],
        intervals=["2h"],
        template_context={"ticker": "TON/USDT"},
    )

    result = await service.build(request)

    assert "Peak ROE: 35.0" in result.prompt_text


@pytest.mark.asyncio
async def test_prompt_builder_prefers_persisted_peak_roe_over_current_roe():
    template = PromptTemplate(
        id=1,
        name="pm-peak-roe-persisted",
        intro="Peak ROE: {peak_roe}",
        response_format="OK",
        quant_fields=["price_current"],
        chart_defaults={
            "data_selections": ["open_positions"],
            "field_selections": {
                "open_positions": ["peak_roe"],
            },
        },
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
        position_origin_service=StubPositionOriginService(
            {
                "TON": ActivePositionOriginRecord(
                    account_id="acc-1",
                    symbol="TON",
                    peak_roe=42.0,
                    exchange_opened_at=datetime(2024, 9, 1, 10, 0, tzinfo=timezone.utc),
                )
            }
        ),
    )

    request = PromptBuildRequest(
        request_id="req-pm-peak-roe-persisted",
        template_id=1,
        trigger_reason="position_management",
        tickers=["TON/USDT"],
        intervals=["2h"],
        template_context={"ticker": "TON/USDT"},
    )

    result = await service.build(request)

    assert "Peak ROE: 42.0" in result.prompt_text


@pytest.mark.asyncio
async def test_prompt_builder_falls_back_to_position_origin_created_at_for_duration(monkeypatch):
    fixed_now = datetime(2024, 9, 1, 12, 0, tzinfo=timezone.utc)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed_now.replace(tzinfo=None)
            return fixed_now.astimezone(tz)

    monkeypatch.setattr(
        "app.application.prompt_builder.service.datetime",
        FixedDateTime,
    )

    template = PromptTemplate(
        id=1,
        name="pm-origin-duration",
        intro="Duration: {duration}",
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
        portfolio_service=StubPortfolioServiceWithPositionNoOpenedAt(),
        risk_config_service=StubRiskConfigService(),
        position_origin_service=StubPositionOriginService(
            {
                "TON": ActivePositionOriginRecord(
                    account_id="acc-1",
                    symbol="TON",
                    anchor_frame="4h",
                    active_tunnel="fast",
                    created_at=datetime(2024, 9, 1, 8, 0, tzinfo=timezone.utc),
                )
            }
        ),
    )

    request = PromptBuildRequest(
        request_id="req-pm-origin-duration",
        template_id=1,
        trigger_reason="position_management",
        tickers=["TON/USDT"],
        intervals=["2h"],
        template_context={"ticker": "TON/USDT"},
    )

    result = await service.build(request)

    assert "Duration: 4h0m" in result.prompt_text


@pytest.mark.asyncio
async def test_prompt_builder_prefers_exchange_opened_at_over_origin_created_at_for_duration(monkeypatch):
    fixed_now = datetime(2024, 9, 1, 12, 0, tzinfo=timezone.utc)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed_now.replace(tzinfo=None)
            return fixed_now.astimezone(tz)

    monkeypatch.setattr(
        "app.application.prompt_builder.service.datetime",
        FixedDateTime,
    )

    template = PromptTemplate(
        id=1,
        name="pm-origin-exchange-duration",
        intro="Duration: {duration}",
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
        position_origin_service=StubPositionOriginService(
            {
                "TON": ActivePositionOriginRecord(
                    account_id="acc-1",
                    symbol="TON",
                    created_at=datetime(2024, 9, 1, 8, 0, tzinfo=timezone.utc),
                    exchange_opened_at=datetime(2024, 9, 1, 11, 0, tzinfo=timezone.utc),
                )
            }
        ),
    )

    request = PromptBuildRequest(
        request_id="req-pm-origin-exchange-duration",
        template_id=1,
        trigger_reason="position_management",
        tickers=["TON/USDT"],
        intervals=["2h"],
        template_context={"ticker": "TON/USDT"},
    )

    result = await service.build(request)

    assert "Duration: 1h0m" in result.prompt_text


@pytest.mark.asyncio
async def test_prompt_builder_uses_completed_position_history_for_recent_completed_trades():
    template = PromptTemplate(
        id=1,
        name="recent-completed",
        intro="Hello",
        response_format="OK",
        quant_fields=["price_current"],
        chart_defaults={"data_selections": ["recent_completed_trades"]},
        is_default=True,
    )
    snapshot = _build_snapshot("BTC")
    service = PromptBuilderService(
        template_repository=StubTemplateRepo(template),
        quant_provider=StubQuantProvider(snapshot),
        chart_preview_service=StubChartGenerator(),
        uploader_service=StubUploaderService(StubUploader()),
        portfolio_service=StubPortfolioServiceWithCompletedTrades(),
        risk_config_service=StubRiskConfigService(),
    )

    request = PromptBuildRequest(
        request_id="req-completed-trades",
        template_id=1,
        trigger_reason="new_resonance",
        tickers=["BTC"],
        intervals=["2h"],
    )

    result = await service.build(request)

    completed = result.data["recent_completed_trades"]["recent_completed_trades"]
    assert len(completed) == 1
    assert "BTC long" in completed[0]
    assert "Entry 100000.0 Exit 101500.0" in completed[0]
    assert "Profit: +15.00 USDT" in completed[0]
