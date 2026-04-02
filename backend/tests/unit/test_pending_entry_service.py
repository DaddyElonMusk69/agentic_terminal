from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.application.pending_entry.service import PendingEntryService
from app.domain.automation.models import AutomationConfig
from app.domain.llm_response_worker.models import ExecutionAction, ExecutionIdea
from app.domain.portfolio.models import ExchangeAccount, Position, PortfolioSnapshot, AccountState, MarketQuote
from app.domain.trade_executor.models import ExecutionResult
from app.infrastructure.db.models import Base
from app.infrastructure.repositories.pending_entry_repository import SqlPendingEntryRepository


class StubAutomationConfigService:
    async def get_config(self) -> AutomationConfig:
        return AutomationConfig(
            execution_mode="production",
            ema_interval_seconds=60,
            quant_interval_seconds=60,
            pending_entry_timeout_seconds=900,
            max_positions=3,
            provider=None,
            model=None,
        )


class StubTradeExecutor:
    def __init__(self) -> None:
        self.decisions: list[ExecutionIdea] = []

    async def execute(self, decision: ExecutionIdea) -> ExecutionResult:
        self.decisions.append(decision)
        return ExecutionResult(success=True, status="filled", order_id="protect-1")


class StubPositionOriginService:
    def __init__(self) -> None:
        self.upserts: list[dict] = []

    async def upsert(self, account_id: str, symbol, anchor_frame, active_tunnel):
        self.upserts.append(
            {
                "account_id": account_id,
                "symbol": symbol,
                "anchor_frame": anchor_frame,
                "active_tunnel": active_tunnel,
            }
        )
        return None


class StubPortfolioService:
    def __init__(self) -> None:
        now = datetime.now(timezone.utc)
        self.account = ExchangeAccount(
            id="acc-1",
            name="Primary",
            exchange="binance",
            is_active=True,
            is_testnet=False,
            created_at=now,
            updated_at=now,
        )
        self.positions: list[Position] = []
        self.open_orders: list[dict] = []
        self.order_lookup: dict[str, dict | None] = {}
        self.canceled: list[tuple[str, str]] = []

    async def get_active_account(self):
        return self.account

    async def get_portfolio_snapshot(self) -> PortfolioSnapshot:
        return PortfolioSnapshot(
            account=self.account,
            state=AccountState(
                account_value=1000.0,
                available_margin=900.0,
                total_margin_used=100.0,
                unrealized_pnl=0.0,
                open_positions_count=len(self.positions),
                total_exposure_pct=10.0,
            ),
            positions=list(self.positions),
        )

    async def get_open_orders(self, symbols=None):
        del symbols
        return list(self.open_orders)

    async def get_order(self, order_id: str, symbol: str):
        del symbol
        return self.order_lookup.get(order_id)

    async def cancel_order(self, order_id: str, symbol: str):
        self.canceled.append((order_id, symbol))
        self.open_orders = [order for order in self.open_orders if str(order.get("id")) != order_id]
        return {"id": order_id, "status": "canceled"}

    async def get_ticker_quotes(self, symbols: list[str]):
        return {symbol: MarketQuote(price=100.0) for symbol in symbols}


@pytest.mark.asyncio
async def test_pending_entry_service_expires_resting_order_after_timeout():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    repository = SqlPendingEntryRepository(sessionmaker)
    portfolio = StubPortfolioService()
    trade_executor = StubTradeExecutor()
    service = PendingEntryService(
        repository=repository,
        portfolio_service=portfolio,
        trade_executor=trade_executor,
        automation_config_service=StubAutomationConfigService(),
        position_origin_service=StubPositionOriginService(),
        outbox=None,
    )

    decision = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG_LIMIT,
        symbol="BTC",
        position_size_usd=100.0,
        limit_price=100.0,
        stop_loss_roe=-0.01,
        take_profit_roe=0.03,
        anchor_frame="4h",
        active_tunnel="slow",
    )
    result = ExecutionResult(
        success=True,
        status="resting",
        order_id="ord-1",
        raw_response={"id": "ord-1", "symbol": "BTC/USDT:USDT", "amount": 1.0, "filled": 0.0},
    )

    record = await service.register_resting_entry(
        decision=decision,
        execution_result=result,
        session_id="session-1",
    )
    assert record is not None

    expired = await repository.update(
        replace(
            record,
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
    )
    portfolio.order_lookup[expired.exchange_order_id] = {"id": "ord-1", "status": "expired"}

    handled = await service.poll_once()
    assert handled == 1

    stored = await repository.get(expired.id)
    assert stored is not None
    assert stored.status == stored.status.EXPIRED


@pytest.mark.asyncio
async def test_pending_entry_service_resets_timeout_when_fill_is_detected_at_expiry_boundary():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    repository = SqlPendingEntryRepository(sessionmaker)
    portfolio = StubPortfolioService()
    trade_executor = StubTradeExecutor()
    service = PendingEntryService(
        repository=repository,
        portfolio_service=portfolio,
        trade_executor=trade_executor,
        automation_config_service=StubAutomationConfigService(),
        position_origin_service=StubPositionOriginService(),
        outbox=None,
    )

    decision = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG_LIMIT,
        symbol="BTC",
        position_size_usd=100.0,
        limit_price=100.0,
        stop_loss_roe=-0.01,
        take_profit_roe=0.03,
        anchor_frame="4h",
        active_tunnel="slow",
    )
    result = ExecutionResult(
        success=True,
        status="resting",
        order_id="ord-timeout-fill",
        raw_response={"id": "ord-timeout-fill", "symbol": "BTC/USDT:USDT", "amount": 1.0, "filled": 0.0},
    )

    record = await service.register_resting_entry(
        decision=decision,
        execution_result=result,
        session_id="session-timeout-fill",
    )
    assert record is not None

    expired = await repository.update(
        replace(
            record,
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
    )
    portfolio.open_orders = [
        {"id": "ord-timeout-fill", "symbol": "BTC/USDT:USDT", "filled": 1.0, "status": "open"}
    ]
    portfolio.order_lookup[expired.exchange_order_id] = {
        "id": "ord-timeout-fill",
        "symbol": "BTC/USDT:USDT",
        "filled": 1.0,
        "status": "closed",
        "average": 100.0,
    }

    handled = await service.poll_once()
    assert handled == 1

    stored = await repository.get(expired.id)
    assert stored is not None
    assert stored.status == stored.status.PROTECTION_PENDING
    assert stored.last_error == "waiting_for_position_visibility"
    assert stored.expires_at > datetime.now(timezone.utc)
    assert portfolio.canceled == []


@pytest.mark.asyncio
async def test_pending_entry_service_cancels_remainder_and_attaches_protection_on_partial_fill():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    repository = SqlPendingEntryRepository(sessionmaker)
    portfolio = StubPortfolioService()
    trade_executor = StubTradeExecutor()
    origin_service = StubPositionOriginService()
    service = PendingEntryService(
        repository=repository,
        portfolio_service=portfolio,
        trade_executor=trade_executor,
        automation_config_service=StubAutomationConfigService(),
        position_origin_service=origin_service,
        outbox=None,
    )

    decision = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG_LIMIT,
        symbol="BTC",
        position_size_usd=200.0,
        limit_price=100.0,
        leverage=5,
        stop_loss_roe=0.0,
        take_profit_roe=0.03,
        anchor_frame="2h",
        active_tunnel="fast",
    )
    result = ExecutionResult(
        success=True,
        status="resting",
        order_id="ord-2",
        raw_response={"id": "ord-2", "symbol": "BTC/USDT:USDT", "amount": 2.0, "filled": 0.0},
    )

    record = await service.register_resting_entry(
        decision=decision,
        execution_result=result,
        session_id="session-2",
    )
    assert record is not None

    portfolio.positions = [
        Position(
            symbol="BTC/USDT",
            direction="long",
            size=1.0,
            entry_price=101.0,
            mark_price=102.0,
            unrealized_pnl=1.0,
            liquidation_price=None,
            margin=20.2,
            leverage=5.0,
        )
    ]
    portfolio.open_orders = [
        {"id": "ord-2", "symbol": "BTC/USDT:USDT", "filled": 1.0, "status": "open"}
    ]

    handled = await service.poll_once()
    assert handled == 1

    stored = await repository.get(record.id)
    assert stored is not None
    assert stored.status == stored.status.PARTIALLY_FILLED
    assert portfolio.canceled == [("ord-2", "BTC/USDT:USDT")]
    assert [decision.action for decision in trade_executor.decisions] == [
        ExecutionAction.UPDATE_SL,
        ExecutionAction.UPDATE_TP,
    ]
    assert origin_service.upserts == [
        {
            "account_id": "acc-1",
            "symbol": "BTC",
            "anchor_frame": "2h",
            "active_tunnel": "fast",
        }
    ]


@pytest.mark.asyncio
async def test_pending_entry_service_attaches_initial_stop_below_entry_for_long_fill():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    repository = SqlPendingEntryRepository(sessionmaker)
    portfolio = StubPortfolioService()
    trade_executor = StubTradeExecutor()
    service = PendingEntryService(
        repository=repository,
        portfolio_service=portfolio,
        trade_executor=trade_executor,
        automation_config_service=StubAutomationConfigService(),
        position_origin_service=StubPositionOriginService(),
        outbox=None,
    )

    decision = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG_LIMIT,
        symbol="BTC",
        position_size_usd=200.0,
        limit_price=100.0,
        leverage=5,
        stop_loss_roe=0.03,
        take_profit_roe=0.08,
    )
    result = ExecutionResult(
        success=True,
        status="resting",
        order_id="ord-3",
        raw_response={"id": "ord-3", "symbol": "BTC/USDT:USDT", "amount": 2.0, "filled": 0.0},
    )

    record = await service.register_resting_entry(
        decision=decision,
        execution_result=result,
        session_id="session-3",
    )
    assert record is not None

    portfolio.positions = [
        Position(
            symbol="BTC/USDT",
            direction="long",
            size=2.0,
            entry_price=101.0,
            mark_price=102.0,
            unrealized_pnl=2.0,
            liquidation_price=None,
            margin=40.4,
            leverage=5.0,
        )
    ]
    portfolio.order_lookup[record.exchange_order_id] = {
        "id": "ord-3",
        "symbol": "BTC/USDT:USDT",
        "filled": 2.0,
        "status": "closed",
        "average": 101.0,
    }

    handled = await service.poll_once()
    assert handled == 1

    assert [item.action for item in trade_executor.decisions] == [
        ExecutionAction.UPDATE_SL,
        ExecutionAction.UPDATE_TP,
    ]
    assert trade_executor.decisions[0].new_stop_loss == 100.39
    assert trade_executor.decisions[1].new_take_profit == 102.62


@pytest.mark.asyncio
async def test_pending_entry_service_keeps_protection_pending_fill_alive_while_waiting_for_position():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    repository = SqlPendingEntryRepository(sessionmaker)
    portfolio = StubPortfolioService()
    trade_executor = StubTradeExecutor()
    service = PendingEntryService(
        repository=repository,
        portfolio_service=portfolio,
        trade_executor=trade_executor,
        automation_config_service=StubAutomationConfigService(),
        position_origin_service=StubPositionOriginService(),
        outbox=None,
    )

    decision = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG,
        symbol="BTC",
        position_size_usd=100.0,
        leverage=5,
        stop_loss_roe=0.03,
        take_profit_roe=0.08,
    )
    result = ExecutionResult(
        success=True,
        status="filled",
        order_id="ord-m1",
        fill_price=101.0,
        filled_size=1.0,
        error="protection_attach_failed: No open position for BTC/USDT:USDT",
        raw_response={"id": "ord-m1", "symbol": "BTC/USDT:USDT", "average": 101.0, "filled": 1.0},
    )

    record = await service.register_protection_pending_entry(
        decision=decision,
        execution_result=result,
        session_id="session-m1",
    )

    assert record is not None
    assert record.status == record.status.PROTECTION_PENDING

    handled = await service.poll_once()
    assert handled == 0

    stored = await repository.get(record.id)
    assert stored is not None
    assert stored.status == stored.status.PROTECTION_PENDING
    assert stored.last_error == "waiting_for_position_visibility"
    assert trade_executor.decisions == []


@pytest.mark.asyncio
async def test_pending_entry_service_attaches_protection_for_market_fill_retry_when_position_appears():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    repository = SqlPendingEntryRepository(sessionmaker)
    portfolio = StubPortfolioService()
    trade_executor = StubTradeExecutor()
    origin_service = StubPositionOriginService()
    service = PendingEntryService(
        repository=repository,
        portfolio_service=portfolio,
        trade_executor=trade_executor,
        automation_config_service=StubAutomationConfigService(),
        position_origin_service=origin_service,
        outbox=None,
    )

    decision = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG,
        symbol="BTC",
        position_size_usd=100.0,
        leverage=5,
        stop_loss_roe=0.03,
        take_profit_roe=0.08,
        anchor_frame="4h",
        active_tunnel="slow",
    )
    result = ExecutionResult(
        success=True,
        status="filled",
        order_id="ord-m2",
        fill_price=101.0,
        filled_size=1.0,
        error="protection_attach_failed: No open position for BTC/USDT:USDT",
        raw_response={"id": "ord-m2", "symbol": "BTC/USDT:USDT", "average": 101.0, "filled": 1.0},
    )

    record = await service.register_protection_pending_entry(
        decision=decision,
        execution_result=result,
        session_id="session-m2",
    )
    assert record is not None

    portfolio.positions = [
        Position(
            symbol="BTC/USDT",
            direction="long",
            size=1.0,
            entry_price=101.0,
            mark_price=102.0,
            unrealized_pnl=1.0,
            liquidation_price=None,
            margin=20.2,
            leverage=5.0,
        )
    ]

    handled = await service.poll_once()
    assert handled == 1

    stored = await repository.get(record.id)
    assert stored is not None
    assert stored.status == stored.status.FILLED
    assert [item.action for item in trade_executor.decisions] == [
        ExecutionAction.UPDATE_SL,
        ExecutionAction.UPDATE_TP,
    ]
    assert trade_executor.decisions[0].new_stop_loss == 100.39
    assert trade_executor.decisions[1].new_take_profit == 102.62
    assert origin_service.upserts == [
        {
            "account_id": "acc-1",
            "symbol": "BTC",
            "anchor_frame": "4h",
            "active_tunnel": "slow",
        }
    ]
