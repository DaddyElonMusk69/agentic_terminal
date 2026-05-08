from __future__ import annotations

from collections import deque
from dataclasses import replace
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.application.auto_add.service import AutoAddService
from app.domain.automation.models import AutomationConfig
from app.domain.auto_add.models import AutoAddStatus, AutoAddTrancheKind, AutoAddTrancheStatus
from app.domain.llm_response_worker.models import ExecutionAction, ExecutionIdea
from app.domain.portfolio.models import AccountState, ExchangeAccount, MarketCandle, Position
from app.domain.trade_executor.models import ExecutionResult
from app.infrastructure.db.models import Base
from app.infrastructure.repositories.auto_add_repository import SqlAutoAddRepository


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
            auto_add_enabled=True,
            auto_add_trigger_atr_multiple=1.0,
            auto_add_tranche_margin_pct=0.80,
            auto_add_max_tranches=2,
            auto_add_protected_stop_roe=0.002,
        )


class StubTradeGuard:
    async def validate(self, decision, **kwargs):  # noqa: ANN001
        del decision, kwargs
        raise AssertionError("auto-add ladder should not use trade guard")


class StubTradeExecutor:
    def __init__(self, stop_market_results: list[ExecutionResult]) -> None:
        self._stop_market_results = deque(stop_market_results)
        self.stop_market_calls: list[dict] = []

    async def place_stop_market_entry(
        self,
        *,
        symbol: str,
        side: str,
        size_usd: float,
        trigger_price: float,
        leverage: int,
    ) -> ExecutionResult:
        self.stop_market_calls.append(
            {
                "symbol": symbol,
                "side": side,
                "size_usd": size_usd,
                "trigger_price": trigger_price,
                "leverage": leverage,
            }
        )
        if self._stop_market_results:
            return self._stop_market_results.popleft()
        return ExecutionResult(success=True, status="resting", order_id="default-order")


class StubPortfolioService:
    def __init__(self, positions: list[Position]) -> None:
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
        self.positions = positions
        self.open_orders: list[dict] = []
        self.positions_error: Exception | None = None
        self.open_orders_error: Exception | None = None
        self.canceled: list[tuple[str, str]] = []
        self.candle_calls = 0

    async def get_active_account(self):
        return self.account

    async def get_positions(self):
        if self.positions_error is not None:
            raise self.positions_error
        return list(self.positions)

    async def get_open_orders(self, symbols=None, *, include_conditional_orders=True):  # noqa: ANN001
        del symbols, include_conditional_orders
        if self.open_orders_error is not None:
            raise self.open_orders_error
        return list(self.open_orders)

    async def cancel_order(self, order_id: str, symbol: str):
        self.canceled.append((order_id, symbol))
        self.open_orders = [
            order
            for order in self.open_orders
            if str(order.get("id") or order.get("orderId") or order.get("algoId")) != order_id
        ]
        return {"id": order_id, "status": "canceled"}

    async def get_candles(self, symbol: str, timeframe: str, limit: int):  # noqa: ARG002
        self.candle_calls += 1
        return _candles(limit)


def _position(
    *,
    symbol: str = "BTC/USDT",
    direction: str = "LONG",
    entry_price: float = 100.0,
    mark_price: float = 100.0,
    size: float = 1.0,
    margin: float = 20.0,
    leverage: float = 5.0,
) -> Position:
    return Position(
        symbol=symbol,
        direction=direction,
        size=size,
        entry_price=entry_price,
        mark_price=mark_price,
        unrealized_pnl=None,
        liquidation_price=None,
        margin=margin,
        leverage=leverage,
    )


def _candles(limit: int) -> list[MarketCandle]:
    candles: list[MarketCandle] = []
    price = 100.0
    for idx in range(limit):
        candles.append(
            MarketCandle(
                timestamp_ms=idx * 60_000,
                open=price,
                high=price + 0.5,
                low=price - 0.5,
                close=price,
                volume=10.0,
            )
        )
    return candles


async def _build_service(
    *,
    positions: list[Position],
    stop_market_results: list[ExecutionResult],
):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    repository = SqlAutoAddRepository(sessionmaker)
    portfolio = StubPortfolioService(positions)
    service = AutoAddService(
        repository=repository,
        portfolio_service=portfolio,
        trade_guard=StubTradeGuard(),
        trade_executor=StubTradeExecutor(stop_market_results),
        automation_config_service=StubAutomationConfigService(),
    )
    return service, repository, portfolio


@pytest.mark.asyncio
async def test_register_fresh_entry_places_stop_market_ladder_once():
    service, repository, portfolio = await _build_service(
        positions=[_position(entry_price=100.0, mark_price=100.2, margin=20.0, leverage=5.0)],
        stop_market_results=[
            ExecutionResult(success=True, status="resting", order_id="ladder-1"),
            ExecutionResult(success=True, status="resting", order_id="ladder-2"),
        ],
    )
    portfolio.open_orders = [
        {
            "id": "sl-1",
            "symbol": "BTC/USDT:USDT",
            "type": "stop_market",
            "stopPrice": 98.0,
            "reduceOnly": True,
            "status": "open",
        }
    ]

    record = await service.register_fresh_entry(
        decision=ExecutionIdea(
            action=ExecutionAction.OPEN_LONG,
            symbol="BTC",
            position_size_usd=100.0,
            leverage=5,
        ),
        execution_result=ExecutionResult(success=True, status="filled", order_id="entry-1", fill_price=100.0),
        session_id="session-1",
        open_positions_before=[],
    )

    assert record is not None
    stored = await repository.get_position(record.id)
    tranches = await repository.list_tranches(record.id)
    assert stored is not None
    assert stored.status == AutoAddStatus.ACTIVE
    assert stored.next_trigger_price == 101.0
    assert portfolio.candle_calls == 1
    assert len(service._trade_executor.stop_market_calls) == 2
    assert service._trade_executor.stop_market_calls[0]["trigger_price"] == 101.0
    assert service._trade_executor.stop_market_calls[1]["trigger_price"] == 102.0
    assert [tranche.tranche_index for tranche in tranches] == [0, 1, 2]
    assert tranches[1].status == AutoAddTrancheStatus.PLACED
    assert tranches[1].exchange_order_id == "ladder-1"
    assert tranches[1].trigger_price == 101.0
    assert tranches[2].exchange_order_id == "ladder-2"


@pytest.mark.asyncio
async def test_poll_once_keeps_missing_order_placed_without_position_size_increase():
    service, repository, portfolio = await _build_service(
        positions=[_position(entry_price=100.0, mark_price=102.2, margin=20.0, leverage=5.0)],
        stop_market_results=[
            ExecutionResult(success=True, status="resting", order_id="ladder-1"),
            ExecutionResult(success=True, status="resting", order_id="ladder-2"),
        ],
    )
    portfolio.open_orders = [
        {
            "id": "sl-1",
            "symbol": "BTC/USDT:USDT",
            "type": "stop_market",
            "stopPrice": 98.0,
            "reduceOnly": True,
            "status": "open",
        }
    ]
    record = await service.register_fresh_entry(
        decision=ExecutionIdea(
            action=ExecutionAction.OPEN_LONG,
            symbol="BTC",
            position_size_usd=100.0,
            leverage=5,
        ),
        execution_result=ExecutionResult(success=True, status="filled", order_id="entry-1", fill_price=100.0),
        session_id="session-1",
        open_positions_before=[],
    )
    assert record is not None

    portfolio.open_orders = [
        {
            "id": "ladder-2",
            "symbol": "BTC/USDT:USDT",
            "type": "stop_market",
            "stopPrice": 102.0,
            "status": "open",
        }
    ]

    handled = await service.poll_once()

    stored = await repository.get_position(record.id)
    tranches = await repository.list_tranches(record.id)
    assert handled == 0
    assert stored is not None
    assert stored.add_count == 0
    assert stored.next_trigger_price == 101.0
    assert tranches[1].status == AutoAddTrancheStatus.PLACED
    assert tranches[1].fill_price is None
    assert tranches[1].filled_quantity is None
    assert tranches[2].status == AutoAddTrancheStatus.PLACED


@pytest.mark.asyncio
async def test_poll_once_resolves_missing_order_when_position_size_increases():
    service, repository, portfolio = await _build_service(
        positions=[_position(entry_price=100.0, mark_price=100.2, size=1.0, margin=20.0, leverage=5.0)],
        stop_market_results=[
            ExecutionResult(success=True, status="resting", order_id="ladder-1"),
            ExecutionResult(success=True, status="resting", order_id="ladder-2"),
        ],
    )
    portfolio.open_orders = [
        {
            "id": "sl-1",
            "symbol": "BTC/USDT:USDT",
            "type": "stop_market",
            "stopPrice": 98.0,
            "reduceOnly": True,
            "status": "open",
        }
    ]
    record = await service.register_fresh_entry(
        decision=ExecutionIdea(
            action=ExecutionAction.OPEN_LONG,
            symbol="BTC",
            position_size_usd=100.0,
            leverage=5,
        ),
        execution_result=ExecutionResult(success=True, status="filled", order_id="entry-1", fill_price=100.0),
        session_id="session-1",
        open_positions_before=[],
    )
    assert record is not None

    portfolio.positions = [_position(entry_price=100.5, mark_price=102.2, size=1.4, margin=28.0, leverage=5.0)]
    portfolio.open_orders = [
        {
            "id": "ladder-2",
            "symbol": "BTC/USDT:USDT",
            "type": "stop_market",
            "stopPrice": 102.0,
            "status": "open",
        }
    ]

    handled = await service.poll_once()

    stored = await repository.get_position(record.id)
    tranches = await repository.list_tranches(record.id)
    assert handled == 1
    assert stored is not None
    assert stored.add_count == 1
    assert stored.expected_quantity == 1.4
    assert stored.next_trigger_price == 102.0
    assert tranches[1].status == AutoAddTrancheStatus.RESOLVED
    assert tranches[1].fill_price == 101.0
    assert tranches[1].filled_quantity == pytest.approx(0.4)
    assert tranches[2].status == AutoAddTrancheStatus.PLACED


@pytest.mark.asyncio
async def test_poll_once_cancels_remaining_orders_when_position_disappears():
    service, repository, portfolio = await _build_service(
        positions=[_position(entry_price=100.0, mark_price=100.2, margin=20.0, leverage=5.0)],
        stop_market_results=[
            ExecutionResult(success=True, status="resting", order_id="ladder-1"),
            ExecutionResult(success=True, status="resting", order_id="ladder-2"),
        ],
    )
    portfolio.open_orders = [
        {
            "id": "sl-1",
            "symbol": "BTC/USDT:USDT",
            "type": "stop_market",
            "stopPrice": 98.0,
            "reduceOnly": True,
            "status": "open",
        }
    ]
    record = await service.register_fresh_entry(
        decision=ExecutionIdea(
            action=ExecutionAction.OPEN_LONG,
            symbol="BTC",
            position_size_usd=100.0,
            leverage=5,
        ),
        execution_result=ExecutionResult(success=True, status="filled", order_id="entry-1", fill_price=100.0),
        session_id="session-1",
        open_positions_before=[],
    )
    assert record is not None

    portfolio.positions = []
    portfolio.open_orders = [
        {"id": "ladder-1", "symbol": "BTC/USDT:USDT", "type": "stop_market", "stopPrice": 101.0, "status": "open"},
        {"id": "ladder-2", "symbol": "BTC/USDT:USDT", "type": "stop_market", "stopPrice": 102.0, "status": "open"},
    ]

    handled = await service.poll_once()

    stored = await repository.get_position(record.id)
    tranches = await repository.list_tranches(record.id)
    assert handled == 1
    assert stored is not None
    assert stored.status == AutoAddStatus.CLOSED
    assert stored.active is False
    assert portfolio.canceled == [("ladder-1", "BTC"), ("ladder-2", "BTC")]
    assert tranches[1].status == AutoAddTrancheStatus.CANCELED
    assert tranches[2].status == AutoAddTrancheStatus.CANCELED


@pytest.mark.asyncio
async def test_poll_once_ignores_position_fetch_errors_and_keeps_ladder_active():
    service, repository, portfolio = await _build_service(
        positions=[_position(entry_price=100.0, mark_price=100.2, margin=20.0, leverage=5.0)],
        stop_market_results=[
            ExecutionResult(success=True, status="resting", order_id="ladder-1"),
            ExecutionResult(success=True, status="resting", order_id="ladder-2"),
        ],
    )
    portfolio.open_orders = [
        {
            "id": "sl-1",
            "symbol": "BTC/USDT:USDT",
            "type": "stop_market",
            "stopPrice": 98.0,
            "reduceOnly": True,
            "status": "open",
        }
    ]
    record = await service.register_fresh_entry(
        decision=ExecutionIdea(
            action=ExecutionAction.OPEN_LONG,
            symbol="BTC",
            position_size_usd=100.0,
            leverage=5,
        ),
        execution_result=ExecutionResult(success=True, status="filled", order_id="entry-1", fill_price=100.0),
        session_id="session-1",
        open_positions_before=[],
    )
    assert record is not None

    portfolio.positions_error = RuntimeError("network error")

    handled = await service.poll_once()

    stored = await repository.get_position(record.id)
    tranches = await repository.list_tranches(record.id)
    assert handled == 0
    assert stored is not None
    assert stored.status == AutoAddStatus.ACTIVE
    assert stored.active is True
    assert stored.add_count == 0
    assert portfolio.canceled == []
    assert tranches[1].status == AutoAddTrancheStatus.PLACED
    assert tranches[2].status == AutoAddTrancheStatus.PLACED


@pytest.mark.asyncio
async def test_snapshot_refresh_skips_tranche_resolution_when_open_orders_are_unavailable():
    service, repository, portfolio = await _build_service(
        positions=[_position(entry_price=100.0, mark_price=100.2, margin=20.0, leverage=5.0)],
        stop_market_results=[
            ExecutionResult(success=True, status="resting", order_id="ladder-1"),
            ExecutionResult(success=True, status="resting", order_id="ladder-2"),
        ],
    )
    portfolio.open_orders = [
        {
            "id": "sl-1",
            "symbol": "BTC/USDT:USDT",
            "type": "stop_market",
            "stopPrice": 98.0,
            "reduceOnly": True,
            "status": "open",
        }
    ]
    record = await service.register_fresh_entry(
        decision=ExecutionIdea(
            action=ExecutionAction.OPEN_LONG,
            symbol="BTC",
            position_size_usd=100.0,
            leverage=5,
        ),
        execution_result=ExecutionResult(success=True, status="filled", order_id="entry-1", fill_price=100.0),
        session_id="session-1",
        open_positions_before=[],
    )
    assert record is not None

    portfolio.open_orders_error = RuntimeError("network error")

    snapshots = await service.list_position_snapshots_for_active_account(symbols=["BTC"])

    stored = await repository.get_position(record.id)
    tranches = await repository.list_tranches(record.id)
    assert len(snapshots) == 1
    assert snapshots[0].record.status == AutoAddStatus.ACTIVE
    assert snapshots[0].tranches[1].status == AutoAddTrancheStatus.PLACED
    assert snapshots[0].tranches[2].status == AutoAddTrancheStatus.PLACED
    assert stored is not None
    assert stored.status == AutoAddStatus.ACTIVE
    assert stored.add_count == 0
    assert tranches[1].status == AutoAddTrancheStatus.PLACED
    assert tranches[2].status == AutoAddTrancheStatus.PLACED


@pytest.mark.asyncio
async def test_poll_once_treats_zero_size_position_as_closed_and_cancels_ladder():
    service, repository, portfolio = await _build_service(
        positions=[_position(entry_price=100.0, mark_price=100.2, margin=20.0, leverage=5.0)],
        stop_market_results=[
            ExecutionResult(success=True, status="resting", order_id="ladder-1"),
            ExecutionResult(success=True, status="resting", order_id="ladder-2"),
        ],
    )
    portfolio.open_orders = [
        {
            "id": "sl-1",
            "symbol": "BTC/USDT:USDT",
            "type": "stop_market",
            "stopPrice": 98.0,
            "reduceOnly": True,
            "status": "open",
        }
    ]
    record = await service.register_fresh_entry(
        decision=ExecutionIdea(
            action=ExecutionAction.OPEN_LONG,
            symbol="BTC",
            position_size_usd=100.0,
            leverage=5,
        ),
        execution_result=ExecutionResult(success=True, status="filled", order_id="entry-1", fill_price=100.0),
        session_id="session-1",
        open_positions_before=[],
    )
    assert record is not None

    portfolio.positions = [_position(size=0.0, margin=0.0, leverage=5.0)]
    portfolio.open_orders = [
        {"id": "ladder-1", "symbol": "BTC/USDT:USDT", "type": "stop_market", "stopPrice": 101.0, "status": "open"},
        {"id": "ladder-2", "symbol": "BTC/USDT:USDT", "type": "stop_market", "stopPrice": 102.0, "status": "open"},
    ]

    handled = await service.poll_once()

    stored = await repository.get_position(record.id)
    tranches = await repository.list_tranches(record.id)
    assert handled == 1
    assert stored is not None
    assert stored.status == AutoAddStatus.CLOSED
    assert stored.active is False
    assert portfolio.canceled == [("ladder-1", "BTC"), ("ladder-2", "BTC")]
    assert tranches[1].status == AutoAddTrancheStatus.CANCELED
    assert tranches[2].status == AutoAddTrancheStatus.CANCELED


@pytest.mark.asyncio
async def test_waiting_record_arms_when_limit_fill_position_becomes_visible():
    service, repository, portfolio = await _build_service(
        positions=[],
        stop_market_results=[
            ExecutionResult(success=True, status="resting", order_id="ladder-1"),
            ExecutionResult(success=True, status="resting", order_id="ladder-2"),
        ],
    )

    record = await service.register_limit_fill_after_protection(
        symbol="BTC",
        side="LONG",
        session_id="session-limit",
    )
    assert record is not None
    stored_before = await repository.get_position(record.id)
    assert stored_before is not None
    assert stored_before.status == AutoAddStatus.WAITING_PROTECTION

    portfolio.positions = [_position(entry_price=100.0, mark_price=100.5, margin=20.0, leverage=5.0)]
    portfolio.open_orders = [
        {
            "id": "sl-1",
            "symbol": "BTC/USDT:USDT",
            "type": "stop_market",
            "stopPrice": 98.0,
            "reduceOnly": True,
            "status": "open",
        }
    ]

    handled = await service.poll_once()

    stored_after = await repository.get_position(record.id)
    tranches = await repository.list_tranches(record.id)
    assert handled == 1
    assert stored_after is not None
    assert stored_after.status == AutoAddStatus.ACTIVE
    assert stored_after.next_trigger_price == 101.0
    assert tranches[1].status == AutoAddTrancheStatus.PLACED
    assert tranches[2].status == AutoAddTrancheStatus.PLACED


@pytest.mark.asyncio
async def test_snapshot_does_not_complete_waiting_record_before_ladder_is_armed():
    service, repository, portfolio = await _build_service(
        positions=[],
        stop_market_results=[
            ExecutionResult(success=True, status="resting", order_id="ladder-1"),
            ExecutionResult(success=True, status="resting", order_id="ladder-2"),
        ],
    )

    record = await service.register_limit_fill_after_protection(
        symbol="BTC",
        side="LONG",
        session_id="session-limit",
    )
    assert record is not None

    portfolio.positions = [_position(entry_price=100.0, mark_price=100.5, margin=20.0, leverage=5.0)]

    snapshots = await service.list_position_snapshots_for_active_account(symbols=["BTC"])

    stored = await repository.get_position(record.id)
    tranches = await repository.list_tranches(record.id)
    assert len(snapshots) == 1
    assert snapshots[0].record.status == AutoAddStatus.WAITING_PROTECTION
    assert stored is not None
    assert stored.status == AutoAddStatus.WAITING_PROTECTION
    assert stored.active is True
    assert stored.add_count == 0
    assert len(tranches) == 1
    assert tranches[0].status == AutoAddTrancheStatus.INITIAL


@pytest.mark.asyncio
async def test_poll_once_arms_active_record_without_add_tranches():
    service, repository, portfolio = await _build_service(
        positions=[],
        stop_market_results=[
            ExecutionResult(success=True, status="resting", order_id="ladder-1"),
            ExecutionResult(success=True, status="resting", order_id="ladder-2"),
        ],
    )

    record = await service.register_limit_fill_after_protection(
        symbol="BTC",
        side="LONG",
        session_id="session-limit",
    )
    assert record is not None

    await repository.update_position(
        replace(
            record,
            status=AutoAddStatus.ACTIVE,
            active=True,
            next_trigger_price=None,
        )
    )
    portfolio.positions = [_position(entry_price=100.0, mark_price=100.5, margin=20.0, leverage=5.0)]
    portfolio.open_orders = [
        {
            "id": "sl-1",
            "symbol": "BTC/USDT:USDT",
            "type": "stop_market",
            "stopPrice": 98.0,
            "reduceOnly": True,
            "status": "open",
        }
    ]

    handled = await service.poll_once()

    stored_after = await repository.get_position(record.id)
    tranches = await repository.list_tranches(record.id)
    assert handled == 1
    assert stored_after is not None
    assert stored_after.status == AutoAddStatus.ACTIVE
    assert stored_after.active is True
    assert stored_after.next_trigger_price == 101.0
    assert [tranche.tranche_index for tranche in tranches] == [0, 1, 2]
    assert tranches[1].status == AutoAddTrancheStatus.PLACED
    assert tranches[2].status == AutoAddTrancheStatus.PLACED
    assert len(service._trade_executor.stop_market_calls) == 2


@pytest.mark.asyncio
async def test_poll_once_recovers_premature_completed_initial_only_record():
    service, repository, portfolio = await _build_service(
        positions=[],
        stop_market_results=[
            ExecutionResult(success=True, status="resting", order_id="ladder-1"),
            ExecutionResult(success=True, status="resting", order_id="ladder-2"),
        ],
    )

    record = await service.register_limit_fill_after_protection(
        symbol="BTC",
        side="LONG",
        session_id="session-limit",
    )
    assert record is not None
    await repository.update_position(
        replace(
            record,
            status=AutoAddStatus.COMPLETED,
            active=False,
            resolved_at=datetime.now(timezone.utc),
            last_error=None,
        )
    )

    portfolio.positions = [_position(entry_price=100.0, mark_price=100.5, margin=20.0, leverage=5.0)]
    portfolio.open_orders = [
        {
            "id": "sl-1",
            "symbol": "BTC/USDT:USDT",
            "type": "stop_market",
            "stopPrice": 98.0,
            "reduceOnly": True,
            "status": "open",
        }
    ]

    handled = await service.poll_once()

    stored = await repository.get_position(record.id)
    tranches = await repository.list_tranches(record.id)
    assert handled == 1
    assert stored is not None
    assert stored.status == AutoAddStatus.ACTIVE
    assert stored.active is True
    assert stored.next_trigger_price == 101.0
    assert [tranche.tranche_index for tranche in tranches] == [0, 1, 2]
    assert tranches[1].status == AutoAddTrancheStatus.PLACED
    assert tranches[2].status == AutoAddTrancheStatus.PLACED
    assert len(service._trade_executor.stop_market_calls) == 2


@pytest.mark.asyncio
async def test_snapshot_does_not_complete_failed_add_tranches():
    service, repository, portfolio = await _build_service(
        positions=[_position(entry_price=100.0, mark_price=100.5, margin=20.0, leverage=5.0)],
        stop_market_results=[
            ExecutionResult(success=False, status="error", error="exchange_rejected"),
            ExecutionResult(success=False, status="error", error="exchange_rejected"),
        ],
    )
    portfolio.open_orders = [
        {
            "id": "sl-1",
            "symbol": "BTC/USDT:USDT",
            "type": "stop_market",
            "stopPrice": 98.0,
            "reduceOnly": True,
            "status": "open",
        }
    ]

    record = await service.register_fresh_entry(
        decision=ExecutionIdea(
            action=ExecutionAction.OPEN_LONG,
            symbol="BTC",
            position_size_usd=100.0,
            leverage=5,
        ),
        execution_result=ExecutionResult(success=True, status="filled", order_id="entry-1", fill_price=100.0),
        session_id="session-1",
        open_positions_before=[],
    )
    assert record is not None

    snapshots = await service.list_position_snapshots_for_active_account(symbols=["BTC"])

    stored = await repository.get_position(record.id)
    tranches = await repository.list_tranches(record.id)
    assert len(snapshots) == 1
    assert snapshots[0].record.status == AutoAddStatus.ERROR
    assert stored is not None
    assert stored.status == AutoAddStatus.ERROR
    assert stored.active is False
    assert stored.last_error == "tranche_1:exchange_rejected; tranche_2:exchange_rejected"
    assert tranches[1].status == AutoAddTrancheStatus.FAILED
    assert tranches[2].status == AutoAddTrancheStatus.FAILED


@pytest.mark.asyncio
async def test_poll_once_recovers_unconfirmed_resolved_tranches_without_size_increase():
    service, repository, portfolio = await _build_service(
        positions=[_position(entry_price=100.0, mark_price=100.5, size=1.0, margin=20.0, leverage=5.0)],
        stop_market_results=[
            ExecutionResult(success=True, status="resting", order_id="ladder-1"),
            ExecutionResult(success=True, status="resting", order_id="ladder-2"),
            ExecutionResult(success=True, status="resting", order_id="ladder-1-retry"),
            ExecutionResult(success=True, status="resting", order_id="ladder-2-retry"),
        ],
    )
    portfolio.open_orders = [
        {
            "id": "sl-1",
            "symbol": "BTC/USDT:USDT",
            "type": "stop_market",
            "stopPrice": 98.0,
            "reduceOnly": True,
            "status": "open",
        }
    ]
    record = await service.register_fresh_entry(
        decision=ExecutionIdea(
            action=ExecutionAction.OPEN_LONG,
            symbol="BTC",
            position_size_usd=100.0,
            leverage=5,
        ),
        execution_result=ExecutionResult(success=True, status="filled", order_id="entry-1", fill_price=100.0),
        session_id="session-1",
        open_positions_before=[],
    )
    assert record is not None
    tranches_before = await repository.list_tranches(record.id)
    for tranche in tranches_before:
        if tranche.kind == AutoAddTrancheKind.ADD:
            await repository.update_tranche(
                replace(
                    tranche,
                    status=AutoAddTrancheStatus.RESOLVED,
                    fill_price=tranche.trigger_price,
                    filled_quantity=None,
                    fill_time=datetime.now(timezone.utc),
                )
            )
    await repository.update_position(
        replace(
            record,
            status=AutoAddStatus.COMPLETED,
            active=False,
            add_count=2,
            next_trigger_price=None,
            resolved_at=datetime.now(timezone.utc),
        )
    )

    portfolio.open_orders = [
        {
            "id": "sl-1",
            "symbol": "BTC/USDT:USDT",
            "type": "stop_market",
            "stopPrice": 98.0,
            "reduceOnly": True,
            "status": "open",
        }
    ]

    handled = await service.poll_once()

    stored = await repository.get_position(record.id)
    tranches = await repository.list_tranches(record.id)
    assert handled == 1
    assert stored is not None
    assert stored.status == AutoAddStatus.ACTIVE
    assert stored.active is True
    assert stored.add_count == 0
    assert tranches[1].status == AutoAddTrancheStatus.PLACED
    assert tranches[1].exchange_order_id == "ladder-1-retry"
    assert tranches[1].filled_quantity is None
    assert tranches[2].status == AutoAddTrancheStatus.PLACED
    assert tranches[2].exchange_order_id == "ladder-2-retry"
    assert len(service._trade_executor.stop_market_calls) == 4


@pytest.mark.asyncio
async def test_poll_once_recovers_completed_failed_add_tranches_for_retry():
    service, repository, portfolio = await _build_service(
        positions=[_position(entry_price=100.0, mark_price=100.5, size=1.0, margin=20.0, leverage=5.0)],
        stop_market_results=[
            ExecutionResult(success=False, status="error", error="temporary_rejection"),
            ExecutionResult(success=False, status="error", error="temporary_rejection"),
            ExecutionResult(success=True, status="resting", order_id="ladder-1-retry"),
            ExecutionResult(success=True, status="resting", order_id="ladder-2-retry"),
        ],
    )
    portfolio.open_orders = [
        {
            "id": "sl-1",
            "symbol": "BTC/USDT:USDT",
            "type": "stop_market",
            "stopPrice": 98.0,
            "reduceOnly": True,
            "status": "open",
        }
    ]
    record = await service.register_fresh_entry(
        decision=ExecutionIdea(
            action=ExecutionAction.OPEN_LONG,
            symbol="BTC",
            position_size_usd=100.0,
            leverage=5,
        ),
        execution_result=ExecutionResult(success=True, status="filled", order_id="entry-1", fill_price=100.0),
        session_id="session-1",
        open_positions_before=[],
    )
    assert record is not None
    failed_record = await repository.get_position(record.id)
    assert failed_record is not None
    await repository.update_position(
        replace(
            failed_record,
            status=AutoAddStatus.COMPLETED,
            active=False,
            add_count=0,
            next_trigger_price=None,
            resolved_at=datetime.now(timezone.utc),
            last_error=None,
        )
    )

    handled = await service.poll_once()

    stored = await repository.get_position(record.id)
    tranches = await repository.list_tranches(record.id)
    assert handled == 1
    assert stored is not None
    assert stored.status == AutoAddStatus.ACTIVE
    assert stored.active is True
    assert stored.add_count == 0
    assert tranches[1].status == AutoAddTrancheStatus.PLACED
    assert tranches[1].exchange_order_id == "ladder-1-retry"
    assert tranches[2].status == AutoAddTrancheStatus.PLACED
    assert tranches[2].exchange_order_id == "ladder-2-retry"
    assert len(service._trade_executor.stop_market_calls) == 4
