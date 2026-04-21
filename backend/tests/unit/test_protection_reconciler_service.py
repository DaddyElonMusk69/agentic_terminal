from datetime import datetime, timedelta, timezone

import pytest

from app.application.protection_reconciler.service import ProtectionReconcilerService
from app.domain.llm_response_worker.models import ExecutionAction
from app.domain.portfolio.models import ExchangeAccount
from app.domain.position_origin.models import ActivePositionOriginRecord
from app.domain.trade_executor.models import ExecutionResult


class StubPosition:
    def __init__(self, *, symbol: str, direction: str, entry_price: float, leverage: float, size: float = 1.0) -> None:
        self.symbol = symbol
        self.direction = direction
        self.entry_price = entry_price
        self.leverage = leverage
        self.size = size


class StubPortfolioSnapshot:
    def __init__(self, positions) -> None:  # noqa: ANN001
        self.positions = positions


class StubPortfolioService:
    def __init__(self) -> None:
        self.positions = []
        self.open_orders = []

    async def get_active_account(self):
        now = datetime.now(timezone.utc)
        return ExchangeAccount(
            id="acc-1",
            name="Primary",
            exchange="binance",
            is_active=True,
            is_testnet=False,
            created_at=now,
            updated_at=now,
        )

    async def get_portfolio_snapshot(self):
        return StubPortfolioSnapshot(list(self.positions))

    async def get_open_orders(self, symbols=None):  # noqa: ANN001
        return list(self.open_orders)


class StubPositionOriginService:
    def __init__(self, rows: dict[str, ActivePositionOriginRecord]) -> None:
        self.rows = rows
        self.prune_calls: list[tuple[str, list[str]]] = []

    async def prune_missing(self, account_id: str, live_symbols: list[str]):
        self.prune_calls.append((account_id, list(live_symbols)))
        return 0

    async def get_many(self, account_id: str, symbols: list[str]):  # noqa: ARG002
        return {symbol: self.rows[symbol] for symbol in symbols if symbol in self.rows}

    async def sync_live_positions(self, account_id: str, positions):  # noqa: ARG002, ANN001
        symbols = []
        for position in positions:
            symbol = str(getattr(position, "symbol", "") or "").upper()
            if symbol.endswith("/USDT"):
                symbol = symbol.split("/", 1)[0]
            if symbol:
                symbols.append(symbol)
        return {symbol: self.rows[symbol] for symbol in symbols if symbol in self.rows}


class StubTradeExecutor:
    def __init__(self, results=None):  # noqa: ANN001
        self.results = list(results or [])
        self.decisions = []

    async def execute(self, decision):  # noqa: ANN001
        self.decisions.append(decision)
        if self.results:
            return self.results.pop(0)
        return ExecutionResult(success=True, status="filled", order_id="ok")


class StubOutbox:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def enqueue_event(self, topic: str, payload: dict):  # noqa: ANN001
        self.events.append((topic, payload))


class StubAutoAddService:
    def __init__(self) -> None:
        self.live_symbol_calls: list[list[str]] = []

    async def cancel_missing_parent_positions(self, live_symbols: list[str]) -> int:
        self.live_symbol_calls.append(list(live_symbols))
        return 0


@pytest.mark.asyncio
async def test_protection_reconciler_restores_missing_sl_and_tp():
    position_origin = ActivePositionOriginRecord(
        account_id="acc-1",
        symbol="BTC",
        anchor_frame="4h",
        active_tunnel="fast",
        stop_loss_roe=0.01,
        take_profit_roe=0.03,
    )
    portfolio = StubPortfolioService()
    portfolio.positions = [
        StubPosition(symbol="BTC/USDT", direction="long", entry_price=100.0, leverage=5.0),
    ]
    executor = StubTradeExecutor(
        results=[
            ExecutionResult(success=True, status="filled", order_id="sl-1"),
            ExecutionResult(success=True, status="filled", order_id="tp-1"),
        ]
    )
    outbox = StubOutbox()
    service = ProtectionReconcilerService(
        position_origin_service=StubPositionOriginService({"BTC": position_origin}),
        portfolio_service=portfolio,
        trade_executor=executor,
        outbox=outbox,
    )

    handled = await service.poll_once()

    assert handled == 1
    assert [decision.action for decision in executor.decisions] == [
        ExecutionAction.UPDATE_SL,
        ExecutionAction.UPDATE_TP,
    ]
    assert executor.decisions[0].new_stop_loss == pytest.approx(99.8)
    assert executor.decisions[1].new_take_profit == pytest.approx(100.6)


@pytest.mark.asyncio
async def test_protection_reconciler_restores_only_missing_tp_when_stop_exists():
    position_origin = ActivePositionOriginRecord(
        account_id="acc-1",
        symbol="BTC",
        stop_loss_roe=0.01,
        take_profit_roe=0.03,
    )
    portfolio = StubPortfolioService()
    portfolio.positions = [
        StubPosition(symbol="BTC/USDT", direction="long", entry_price=100.0, leverage=5.0),
    ]
    portfolio.open_orders = [
        {"symbol": "BTC/USDT", "type": "stop_market", "stopPrice": 99.8},
    ]
    executor = StubTradeExecutor(
        results=[ExecutionResult(success=True, status="filled", order_id="tp-1")]
    )
    service = ProtectionReconcilerService(
        position_origin_service=StubPositionOriginService({"BTC": position_origin}),
        portfolio_service=portfolio,
        trade_executor=executor,
        outbox=StubOutbox(),
    )

    handled = await service.poll_once()

    assert handled == 1
    assert len(executor.decisions) == 1
    assert executor.decisions[0].action == ExecutionAction.UPDATE_TP
    assert executor.decisions[0].new_take_profit == pytest.approx(100.6)


@pytest.mark.asyncio
async def test_protection_reconciler_does_not_prune_on_first_empty_snapshot():
    origin_service = StubPositionOriginService({})
    portfolio = StubPortfolioService()
    service = ProtectionReconcilerService(
        position_origin_service=origin_service,
        portfolio_service=portfolio,
        trade_executor=StubTradeExecutor(),
        outbox=StubOutbox(),
    )

    handled = await service.poll_once()

    assert handled == 0
    assert origin_service.prune_calls == []


@pytest.mark.asyncio
async def test_protection_reconciler_prunes_after_empty_snapshot_grace_period():
    origin_service = StubPositionOriginService({})
    portfolio = StubPortfolioService()
    service = ProtectionReconcilerService(
        position_origin_service=origin_service,
        portfolio_service=portfolio,
        trade_executor=StubTradeExecutor(),
        outbox=StubOutbox(),
    )
    service._empty_snapshot_started_at["acc-1"] = datetime.now(timezone.utc) - timedelta(
        seconds=service.EMPTY_SNAPSHOT_PRUNE_GRACE_SECONDS + 1
    )

    handled = await service.poll_once()

    assert handled == 0
    assert origin_service.prune_calls == [("acc-1", [])]


@pytest.mark.asyncio
async def test_protection_reconciler_uses_live_snapshot_for_auto_add_cleanup():
    portfolio = StubPortfolioService()
    portfolio.positions = [
        StubPosition(symbol="BTC/USDT", direction="long", entry_price=100.0, leverage=5.0, size=1.0),
        StubPosition(symbol="ETH/USDT", direction="long", entry_price=10.0, leverage=3.0, size=0.0),
    ]
    auto_add = StubAutoAddService()
    service = ProtectionReconcilerService(
        position_origin_service=StubPositionOriginService({}),
        portfolio_service=portfolio,
        trade_executor=StubTradeExecutor(),
        auto_add_service=auto_add,
        outbox=StubOutbox(),
    )

    handled = await service.poll_once()

    assert handled == 0
    assert auto_add.live_symbol_calls == [["BTC"]]
