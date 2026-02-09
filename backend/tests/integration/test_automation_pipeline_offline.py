from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.application.automation.llm_queue_service import LlmQueueService
from app.application.automation.llm_queue_worker import LlmQueueWorker
from app.application.automation.order_queue_service import OrderQueueService
from app.application.automation.order_queue_worker import OrderQueueWorker
from app.application.automation.pipeline import AutomationPipelineService
from app.application.automation.prompt_pipeline_worker import PromptPipelineWorker
from app.application.bus.outbox_service import OutboxService
from app.application.circuit_breaker.service import CircuitBreakerService
from app.application.ema_scanner.service import EmaScannerService
from app.application.ema_state_manager.service import EmaStateManagerService
from app.application.prompt_builder.queue_service import PromptBuildQueueService
from app.application.prompt_builder.service import PromptBuilderService
from app.application.quant_scanner.service import QuantDataCache, QuantScannerService
from app.domain.ema_scanner.models import EmaScannerConfig
from app.domain.ema_state_manager.models import DEFAULT_EMA_STATE_MANAGER_CONFIG
from app.domain.ema_state_manager.service import EmaStateManager
from app.domain.llm_caller.models import LlmCallResponse
from app.domain.llm_pipeline.models import LlmExecutionResult
from app.domain.llm_response_worker.models import ExecutionAction, ExecutionIdea, LlmResponseParseResult
from app.domain.portfolio.models import (
    AccountState,
    ExchangeAccount,
    MarketCandle,
    MarketDataPoint,
    MarketQuote,
    OrderBookLevel,
    OrderBookSnapshot,
    FundingRateSnapshot,
    PortfolioSnapshot,
)
from app.domain.prompt_builder.models import PromptTemplate
from app.domain.trade_executor.models import ExecutionResult
from app.domain.trade_guard.guard import GuardResult
from app.domain.quant_scanner.models import QuantScannerConfig
from app.infrastructure.bus.outbox_repository import OutboxRepository
from app.infrastructure.db.models import Base
from app.infrastructure.db.models.order_queue import OrderQueueRequestModel
from app.infrastructure.repositories.llm_queue_repository import LlmQueueItem, LlmQueueRepository
from app.infrastructure.repositories.order_queue_repository import OrderQueueItem, OrderQueueRepository
from app.infrastructure.repositories.prompt_build_queue_repository import (
    PromptBuildQueueItem,
    PromptBuildQueueRepository,
)


class FakeConnector:
    def __init__(self, candles: list[MarketCandle], price: float) -> None:
        self._candles = candles
        self._price = price

    async def fetch_candles(self, symbol: str, timeframe: str, limit: int) -> list[MarketCandle]:
        return list(self._candles[-limit:])

    async def fetch_ticker_price(self, symbol: str) -> Optional[float]:
        return self._price

    async def fetch_ticker_quote(self, symbol: str) -> Optional[MarketQuote]:
        if self._price is None:
            return None
        return MarketQuote(price=self._price, change_percent=None)

    async def fetch_ticker_quotes(self, symbols: list[str]) -> dict[str, MarketQuote]:
        if self._price is None:
            return {}
        return {symbol: MarketQuote(price=self._price, change_percent=None) for symbol in symbols}

    async def fetch_open_interest_history(
        self, symbol: str, timeframe: str, limit: int
    ) -> list[MarketDataPoint]:
        base = int(self._candles[-limit].timestamp_ms)
        return [
            MarketDataPoint(timestamp_ms=base + idx * 60_000, value=1000 + idx)
            for idx in range(limit)
        ]

    async def fetch_order_book(self, symbol: str, limit: int) -> OrderBookSnapshot:
        bids = [OrderBookLevel(price=99.5, size=10), OrderBookLevel(price=99.0, size=8)]
        asks = [OrderBookLevel(price=100.5, size=12), OrderBookLevel(price=101.0, size=9)]
        return OrderBookSnapshot(
            symbol=symbol,
            timestamp_ms=int(self._candles[-1].timestamp_ms),
            bids=bids,
            asks=asks,
        )

    async def fetch_funding_rate(self, symbol: str) -> FundingRateSnapshot:
        return FundingRateSnapshot(rate=0.0001, timestamp_ms=int(self._candles[-1].timestamp_ms))


def _ensure_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class UtcPromptBuildQueueRepository(PromptBuildQueueRepository):
    async def claim_next(self) -> Optional[PromptBuildQueueItem]:
        item = await super().claim_next()
        if item is None:
            return None
        return PromptBuildQueueItem(
            id=item.id,
            payload=item.payload,
            status=item.status,
            created_at=_ensure_utc(item.created_at),
            expires_at=_ensure_utc(item.expires_at),
        )


class UtcLlmQueueRepository(LlmQueueRepository):
    async def claim_next(self) -> Optional[LlmQueueItem]:
        item = await super().claim_next()
        if item is None:
            return None
        return LlmQueueItem(
            id=item.id,
            payload=item.payload,
            status=item.status,
            created_at=_ensure_utc(item.created_at),
            expires_at=_ensure_utc(item.expires_at),
        )


class UtcOrderQueueRepository(OrderQueueRepository):
    async def claim_next(self) -> Optional[OrderQueueItem]:
        item = await super().claim_next()
        if item is None:
            return None
        return OrderQueueItem(
            id=item.id,
            payload=item.payload,
            status=item.status,
            created_at=_ensure_utc(item.created_at),
            expires_at=_ensure_utc(item.expires_at),
        )


class FakePortfolioService:
    def __init__(self, connector: FakeConnector) -> None:
        self._connector = connector

    async def get_active_connector(self) -> FakeConnector:
        return self._connector

    async def get_portfolio_snapshot(self) -> PortfolioSnapshot:
        now = datetime.now(timezone.utc)
        account = ExchangeAccount(
            id="acc-1",
            name="Offline",
            exchange="binance",
            is_active=True,
            is_testnet=True,
            created_at=now,
            updated_at=now,
        )
        state = AccountState(
            account_value=10_000,
            available_margin=9_000,
            total_margin_used=1_000,
            unrealized_pnl=0.0,
            open_positions_count=0,
            total_exposure_pct=0.0,
        )
        return PortfolioSnapshot(account=account, state=state, positions=[])

    async def get_daily_pnl(self):
        class _DailyPnl:
            realized_pnl = 0.0
            trade_count = 0

        return _DailyPnl()

    async def get_open_orders(self):
        return []

    async def get_recent_trades(self, limit):  # noqa: ANN001
        return []


class FakeNetflowService:
    def is_configured(self) -> bool:
        return False

    async def fetch_raw(self, symbol: str) -> Optional[dict]:
        return None

    def build_metrics(self, raw_data: Optional[dict], timeframe: str):
        return None


class StubEmaConfigService:
    async def build_config(self, quote_asset: str = "USDT") -> EmaScannerConfig:
        return EmaScannerConfig(
            assets=["BTC"],
            timeframes=["2h", "4h"],
            ema_lengths=[3],
            tolerance_pct=0.5,
            quote_asset=quote_asset,
            min_candles=3,
            candles_multiplier=1,
            max_candles=50,
        )


class StubQuantConfigService:
    async def build_config(self, quote_asset: str = "USDT") -> QuantScannerConfig:
        return QuantScannerConfig(
            assets=["BTC"],
            timeframes=["2h", "4h"],
            quote_asset=quote_asset,
        )


class StubStateConfigService:
    async def get_config(self):
        return DEFAULT_EMA_STATE_MANAGER_CONFIG


class StubTemplateRepository:
    def __init__(self, template: PromptTemplate) -> None:
        self._template = template

    async def get_by_id(self, template_id: int) -> Optional[PromptTemplate]:
        if template_id == self._template.id:
            return self._template
        return None

    async def get_default(self) -> Optional[PromptTemplate]:
        return self._template


class StubChartPreviewService:
    def render_with_overlays(self, symbol, interval, candle_limit, overlays=None):  # noqa: ANN001
        return b"fake-chart"


class StubRiskConfigService:
    async def get_config(self):
        class _RiskConfig:
            exposure_pct = 20.0
            final_goal_usd = 0.0
            goal_deadline = None

        return _RiskConfig()


class StubUploader:
    async def upload(self, image_bytes: bytes, name: str) -> Optional[str]:
        return f"https://example.com/{name}.png"

    async def close(self) -> None:
        return None


class StubUploaderService:
    def __init__(self) -> None:
        self._uploader = StubUploader()

    async def get_uploader(self) -> StubUploader:
        return self._uploader


class FakeLlmExecutionService:
    async def execute(self, request) -> LlmExecutionResult:
        idea = ExecutionIdea(
            action=ExecutionAction.OPEN_LONG,
            symbol="BTC",
            position_size_usd=100,
            confidence=80,
        )
        parse_result = LlmResponseParseResult(success=True, ideas=[idea], considerations=[])
        response = LlmCallResponse(
            content='{"action": "OPEN_LONG", "symbol": "BTC"}',
            model=request.model,
            tokens_used=10,
            latency_ms=1.0,
        )
        return LlmExecutionResult(call_response=response, parse_result=parse_result)


class FakeTradeGuardService:
    async def validate(
        self,
        decision: ExecutionIdea,
        account_state: Optional[dict] = None,
        market_data: Optional[dict] = None,
        open_orders: Optional[list] = None,
        open_positions: Optional[list] = None,
        price_fetcher: Optional[Any] = None,
        tradeable_symbols: Optional[set] = None,
    ) -> GuardResult:
        return GuardResult(is_valid=True, decision=decision)


class FakeTradeExecutorService:
    async def execute(self, decision: ExecutionIdea) -> ExecutionResult:
        return ExecutionResult(success=True, status="executed", order_id="order-1")


def _build_candles(count: int) -> list[MarketCandle]:
    base_ts = 1_700_000_000_000
    candles: list[MarketCandle] = []
    for idx in range(count):
        ts = base_ts + idx * 60_000
        candles.append(MarketCandle(ts, 100, 101, 99, 100, 10))
    return candles


@pytest.mark.asyncio
async def test_offline_automation_pipeline_end_to_end():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    prompt_repo = UtcPromptBuildQueueRepository(sessionmaker)
    llm_repo = UtcLlmQueueRepository(sessionmaker)
    order_repo = UtcOrderQueueRepository(sessionmaker)
    outbox_repo = OutboxRepository(sessionmaker)

    prompt_queue = PromptBuildQueueService(prompt_repo)
    llm_queue = LlmQueueService(llm_repo)
    order_queue = OrderQueueService(order_repo)
    outbox = OutboxService(outbox_repo)

    candles = _build_candles(12)
    connector = FakeConnector(candles, price=100)
    portfolio_service = FakePortfolioService(connector)

    ema_scanner = EmaScannerService(portfolio_service)
    ema_config = StubEmaConfigService()
    ema_state_manager = EmaStateManagerService(StubStateConfigService(), EmaStateManager())

    quant_scanner = QuantScannerService(
        cache=QuantDataCache(),
        portfolio_service=portfolio_service,
        netflow_service=FakeNetflowService(),
    )
    quant_config = StubQuantConfigService()

    pipeline = AutomationPipelineService(
        ema_scanner=ema_scanner,
        ema_config=ema_config,
        ema_state_manager=ema_state_manager,
        quant_scanner=quant_scanner,
        quant_config=quant_config,
        prompt_queue=prompt_queue,
        outbox=outbox,
        portfolio_service=portfolio_service,
    )

    quant_result = await pipeline.run_quant_cycle(limit=10)
    assert quant_result["snapshots"] > 0

    ema_result = await pipeline.run_ema_cycle()
    assert ema_result["queued"] > 0

    template = PromptTemplate(
        id=1,
        name="default",
        intro="ROLE",
        response_format="FORMAT",
        is_default=True,
    )
    prompt_builder = PromptBuilderService(
        template_repository=StubTemplateRepository(template),
        quant_provider=quant_scanner,
        chart_preview_service=StubChartPreviewService(),
        uploader_service=StubUploaderService(),
        portfolio_service=portfolio_service,
        risk_config_service=StubRiskConfigService(),
        upload_concurrency=1,
    )

    prompt_worker = PromptPipelineWorker(prompt_repo, prompt_builder, llm_queue, outbox)
    assert await prompt_worker.process_next() is True

    llm_worker = LlmQueueWorker(llm_repo, FakeLlmExecutionService(), order_queue, outbox)
    assert await llm_worker.process_next() is True

    order_worker = OrderQueueWorker(
        order_repo,
        FakeTradeGuardService(),
        CircuitBreakerService(),
        FakeTradeExecutorService(),
        outbox,
    )
    assert await order_worker.process_next() is True

    async with sessionmaker() as session:
        result = await session.execute(select(OrderQueueRequestModel))
        rows = result.scalars().all()
        assert len(rows) == 1
        assert rows[0].status == "done"
        assert rows[0].result is not None

    await engine.dispose()
