from datetime import datetime, timedelta, timezone

import pytest

from app.application.automation import topics
from app.application.automation.order_queue_worker import OrderQueueWorker
from app.domain.circuit_breaker.models import CircuitBreakerResult
from app.domain.llm_response_worker.models import ExecutionAction, ExecutionIdea
from app.domain.portfolio.models import ExchangeAccount
from app.domain.trade_executor.models import ExecutionResult
from app.domain.trade_guard.guard import GuardResult
from app.infrastructure.repositories.order_queue_repository import OrderQueueItem


class StubOrderQueueRepository:
    def __init__(self, item: OrderQueueItem | None) -> None:
        self._item = item
        self.done_result = None
        self.failed_error = None
        self.dropped_reason = None

    async def claim_next(self):
        item = self._item
        self._item = None
        return item

    async def mark_done(self, request_id: str, result: dict):
        self.done_result = (request_id, result)

    async def mark_failed(self, request_id: str, error: str):
        self.failed_error = (request_id, error)

    async def mark_dropped(self, request_id: str, reason: str):
        self.dropped_reason = (request_id, reason)


class StubTradeGuard:
    async def validate(self, decision, **kwargs):  # noqa: ANN001
        del kwargs
        return GuardResult(is_valid=True, decision=decision)


class StubMarketCapTradeGuard:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def validate(self, decision, **kwargs):  # noqa: ANN001
        self.calls.append(kwargs)
        max_positions = kwargs.get("max_positions")
        inflight_market_open_count = kwargs.get("inflight_market_open_count", 0)
        open_positions = kwargs.get("open_positions") or []
        live_positions = len(
            {
                str(position.get("symbol") or "").upper()
                for position in open_positions
                if isinstance(position, dict) and position.get("symbol")
            }
        )
        if max_positions is not None and live_positions + inflight_market_open_count > max_positions:
            return GuardResult(
                is_valid=False,
                decision=decision,
                errors=["market position cap reached"],
            )
        return GuardResult(is_valid=True, decision=decision)


class StubCircuitBreaker:
    def evaluate(self, decision):  # noqa: ANN001
        return CircuitBreakerResult(allowed=True, decision=decision)


class StubTradeExecutor:
    def __init__(self, result: ExecutionResult | list[ExecutionResult]) -> None:
        if isinstance(result, list):
            self._results = list(result)
        else:
            self._results = [result]
        self.calls: list = []

    async def execute(self, decision):  # noqa: ANN001
        self.calls.append(decision)
        if not self._results:
            return ExecutionResult(success=False, status="error", error="missing_stub_result")
        if len(self._results) == 1:
            return self._results[0]
        return self._results.pop(0)


class StubPendingEntryService:
    def __init__(self) -> None:
        self.resting_calls: list[dict] = []
        self.protection_calls: list[dict] = []
        self.active_records: list = []
        self.cancel_calls: list[str] = []

    async def register_resting_entry(self, *, decision, execution_result, session_id):  # noqa: ANN001
        self.resting_calls.append(
            {"decision": decision, "execution_result": execution_result, "session_id": session_id}
        )
        return None

    async def register_protection_pending_entry(self, *, decision, execution_result, session_id):  # noqa: ANN001
        self.protection_calls.append(
            {"decision": decision, "execution_result": execution_result, "session_id": session_id}
        )
        return None

    async def list_active_records_for_active_account(self):
        return list(self.active_records)

    async def cancel_pending_entry(self, entry_id: str):
        self.cancel_calls.append(entry_id)
        self.active_records = [entry for entry in self.active_records if getattr(entry, "id", None) != entry_id]
        return None


class StubAutomationConfigService:
    def __init__(self, *, max_positions: int = 3) -> None:
        self.max_positions = max_positions

    async def get_config(self):
        return type("AutomationConfig", (), {"max_positions": self.max_positions})()


class StubAutoAddService:
    def __init__(self) -> None:
        self.register_calls: list[dict] = []
        self.cancel_calls: list[dict] = []

    async def register_fresh_entry(
        self,
        *,
        decision,
        execution_result,
        session_id,
        open_positions_before,
    ):  # noqa: ANN001
        self.register_calls.append(
            {
                "decision": decision,
                "execution_result": execution_result,
                "session_id": session_id,
                "open_positions_before": open_positions_before,
            }
        )
        return None

    async def cancel_for_symbol(self, symbol: str, *, reason: str, final_status=None):  # noqa: ANN001
        self.cancel_calls.append(
            {
                "symbol": symbol,
                "reason": reason,
                "final_status": final_status,
            }
        )
        return None


class StubOutbox:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def enqueue_event(self, topic: str, payload: dict):  # noqa: ANN001
        self.events.append((topic, payload))
        return None


class StubPortfolioSnapshot:
    state = type(
        "State",
        (),
        {
            "account_value": 1000.0,
            "available_margin": 900.0,
            "total_margin_used": 100.0,
            "unrealized_pnl": 0.0,
            "open_positions_count": 0,
            "total_exposure_pct": 10.0,
        },
    )()
    positions = []


class StubPortfolioSnapshotWithPosition(StubPortfolioSnapshot):
    positions = [
        type(
            "Position",
            (),
            {
                "symbol": "BTC/USDT",
                "direction": "long",
                "size": 1.0,
                "entry_price": 100.0,
                "mark_price": 101.0,
                "unrealized_pnl": 1.0,
                "liquidation_price": None,
                "margin": 20.0,
                "leverage": 5.0,
            },
        )()
    ]


class StubPortfolioService:
    snapshot_class = StubPortfolioSnapshot

    def __init__(self) -> None:
        self.open_orders: list[dict] = []
        self.canceled_orders: list[tuple[str, str]] = []

    async def get_portfolio_snapshot(self):
        return self.snapshot_class()

    async def get_open_orders(self, symbols=None, include_conditional_orders=True):  # noqa: ANN001
        del symbols, include_conditional_orders
        return list(self.open_orders)

    async def cancel_order(self, order_id: str, symbol: str):
        self.canceled_orders.append((order_id, symbol))
        self.open_orders = [
            order
            for order in self.open_orders
            if str(order.get("id") or order.get("orderId") or order.get("algoId")) != order_id
        ]
        return {"id": order_id, "symbol": symbol, "status": "canceled"}

    async def get_active_connector(self):
        return type("Connector", (), {})()

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


class StubPositionOriginService:
    def __init__(self) -> None:
        self.upserts: list[dict] = []
        self.deletes: list[dict] = []

    async def upsert(
        self,
        account_id: str,
        symbol,
        anchor_frame=None,
        active_tunnel=None,
        *,
        stop_loss_roe=None,
        take_profit_roe=None,
    ):  # noqa: ANN001
        self.upserts.append(
            {
                "account_id": account_id,
                "symbol": symbol,
                "anchor_frame": anchor_frame,
                "active_tunnel": active_tunnel,
                "stop_loss_roe": stop_loss_roe,
                "take_profit_roe": take_profit_roe,
            }
        )
        return None

    async def delete(self, account_id: str, symbol):  # noqa: ANN001
        self.deletes.append({"account_id": account_id, "symbol": symbol})
        return True


def _build_item(execution_idea: dict) -> OrderQueueItem:
    return OrderQueueItem(
        id="ord-1",
        payload={
            "source_request_id": "src-1",
            "session_id": "session-1",
            "execution_mode": "production",
            "execution_idea": execution_idea,
            "cycle_number": 4,
        },
        status="queued",
        created_at=datetime.now(timezone.utc),
        expires_at=None,
    )


def _build_worker(item: OrderQueueItem, result: ExecutionResult, position_origin_service: StubPositionOriginService):
    return OrderQueueWorker(
        repository=StubOrderQueueRepository(item),
        trade_guard=StubTradeGuard(),
        circuit_breaker=StubCircuitBreaker(),
        trade_executor=StubTradeExecutor(result),
        outbox=StubOutbox(),
        portfolio_service=StubPortfolioService(),
        position_origin_service=position_origin_service,
    )


def _build_worker_with_pending(
    item: OrderQueueItem,
    result: ExecutionResult | list[ExecutionResult],
    position_origin_service: StubPositionOriginService,
    pending_entry_service: StubPendingEntryService,
    trade_guard=None,  # noqa: ANN001
    portfolio_service=None,  # noqa: ANN001
    auto_add_service=None,  # noqa: ANN001
    automation_config_service=None,  # noqa: ANN001
):
    return OrderQueueWorker(
        repository=StubOrderQueueRepository(item),
        trade_guard=trade_guard or StubTradeGuard(),
        circuit_breaker=StubCircuitBreaker(),
        trade_executor=StubTradeExecutor(result),
        outbox=StubOutbox(),
        portfolio_service=portfolio_service or StubPortfolioService(),
        position_origin_service=position_origin_service,
        pending_entry_service=pending_entry_service,
        auto_add_service=auto_add_service,
        automation_config_service=automation_config_service,
    )


def _event_payload(events: list[tuple[str, dict]], topic: str) -> dict:
    for event_topic, payload in events:
        if event_topic == topic:
            return payload
    raise AssertionError(f"missing event {topic}")


@pytest.mark.asyncio
async def test_order_queue_worker_persists_origin_metadata_on_filled_open():
    idea = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG,
        symbol="BTC",
        position_size_usd=100,
        anchor_frame="4h",
        active_tunnel="fast",
    ).to_dict()
    position_origin_service = StubPositionOriginService()
    worker = _build_worker(
        _build_item(idea),
        ExecutionResult(success=True, status="filled", order_id="1", fill_price=100.0),
        position_origin_service,
    )

    handled = await worker.process_next()

    assert handled is True
    assert position_origin_service.upserts == [
        {
            "account_id": "acc-1",
            "symbol": "BTC",
            "anchor_frame": "4h",
            "active_tunnel": "fast",
            "stop_loss_roe": None,
            "take_profit_roe": None,
        }
    ]
    assert position_origin_service.deletes == []


@pytest.mark.asyncio
async def test_order_queue_worker_deletes_origin_metadata_on_filled_close():
    idea = ExecutionIdea(
        action=ExecutionAction.CLOSE,
        symbol="BTC",
    ).to_dict()
    position_origin_service = StubPositionOriginService()
    auto_add_service = StubAutoAddService()
    worker = _build_worker_with_pending(
        _build_item(idea),
        ExecutionResult(success=True, status="filled", order_id="1", fill_price=100.0),
        position_origin_service,
        pending_entry_service=StubPendingEntryService(),
        auto_add_service=auto_add_service,
    )

    handled = await worker.process_next()

    assert handled is True
    assert position_origin_service.upserts == []
    assert position_origin_service.deletes == [{"account_id": "acc-1", "symbol": "BTC"}]
    assert auto_add_service.cancel_calls == [
        {
            "symbol": "BTC",
            "reason": "position_closed",
            "final_status": None,
        }
    ]


@pytest.mark.asyncio
async def test_order_queue_worker_skips_origin_metadata_for_resting_limit_open():
    idea = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG_LIMIT,
        symbol="BTC",
        position_size_usd=100,
        anchor_frame="2h",
        active_tunnel="slow",
    ).to_dict()
    position_origin_service = StubPositionOriginService()
    worker = _build_worker(
        _build_item(idea),
        ExecutionResult(success=True, status="resting", order_id="1"),
        position_origin_service,
    )

    handled = await worker.process_next()

    assert handled is True
    assert position_origin_service.upserts == []
    assert position_origin_service.deletes == []


@pytest.mark.asyncio
async def test_order_queue_worker_skips_origin_metadata_on_failed_execution():
    idea = ExecutionIdea(
        action=ExecutionAction.OPEN_SHORT,
        symbol="BTC",
        position_size_usd=100,
        anchor_frame="8h",
        active_tunnel="mid",
    ).to_dict()
    position_origin_service = StubPositionOriginService()
    worker = _build_worker(
        _build_item(idea),
        ExecutionResult(success=False, status="error", error="boom"),
        position_origin_service,
    )

    handled = await worker.process_next()

    assert handled is True
    assert position_origin_service.upserts == []


@pytest.mark.asyncio
async def test_order_queue_worker_registers_protection_retry_for_fresh_filled_market_open():
    idea = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG,
        symbol="BTC",
        position_size_usd=100,
        stop_loss_roe=0.03,
        take_profit_roe=0.08,
        anchor_frame="4h",
        active_tunnel="slow",
    ).to_dict()
    pending_entry_service = StubPendingEntryService()
    position_origin_service = StubPositionOriginService()
    worker = _build_worker_with_pending(
        _build_item(idea),
        ExecutionResult(
            success=True,
            status="filled",
            order_id="mkt-1",
            fill_price=100.0,
            filled_size=1.0,
            error="protection_attach_failed: No open position for BTC/USDT:USDT",
        ),
        position_origin_service,
        pending_entry_service,
    )

    handled = await worker.process_next()

    assert handled is True
    assert len(pending_entry_service.protection_calls) == 1
    assert pending_entry_service.resting_calls == []


@pytest.mark.asyncio
async def test_order_queue_worker_does_not_register_protection_retry_for_add_on_existing_position():
    idea = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG,
        symbol="BTC",
        position_size_usd=100,
        stop_loss_roe=0.03,
        take_profit_roe=0.08,
    ).to_dict()
    pending_entry_service = StubPendingEntryService()
    position_origin_service = StubPositionOriginService()
    portfolio_service = StubPortfolioService()
    portfolio_service.snapshot_class = StubPortfolioSnapshotWithPosition
    worker = _build_worker_with_pending(
        _build_item(idea),
        ExecutionResult(
            success=True,
            status="filled",
            order_id="mkt-2",
            fill_price=100.0,
            filled_size=1.0,
            error="protection_attach_failed: No open position for BTC/USDT:USDT",
        ),
        position_origin_service,
        pending_entry_service,
        portfolio_service=portfolio_service,
    )

    handled = await worker.process_next()

    assert handled is True
    assert pending_entry_service.protection_calls == []
    assert position_origin_service.deletes == []


@pytest.mark.asyncio
async def test_order_queue_worker_persists_protection_intent_on_filled_open():
    idea = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG,
        symbol="BTC",
        position_size_usd=100,
        stop_loss_roe=0.01,
        take_profit_roe=0.03,
        anchor_frame="4h",
        active_tunnel="slow",
    ).to_dict()
    position_origin_service = StubPositionOriginService()
    worker = _build_worker(
        _build_item(idea),
        ExecutionResult(success=True, status="filled", order_id="1", fill_price=100.0),
        position_origin_service,
    )

    handled = await worker.process_next()

    assert handled is True
    assert position_origin_service.upserts == [
        {
            "account_id": "acc-1",
            "symbol": "BTC",
            "anchor_frame": "4h",
            "active_tunnel": "slow",
            "stop_loss_roe": 0.01,
            "take_profit_roe": 0.03,
        }
    ]


@pytest.mark.asyncio
async def test_order_queue_worker_updates_only_stop_loss_intent_on_update_sl():
    idea = ExecutionIdea(
        action=ExecutionAction.UPDATE_SL,
        symbol="BTC",
        stop_loss_roe=0.02,
    ).to_dict()
    position_origin_service = StubPositionOriginService()
    worker = _build_worker(
        _build_item(idea),
        ExecutionResult(success=True, status="filled", order_id="1"),
        position_origin_service,
    )

    handled = await worker.process_next()

    assert handled is True
    assert position_origin_service.upserts == [
        {
            "account_id": "acc-1",
            "symbol": "BTC",
            "anchor_frame": None,
            "active_tunnel": None,
            "stop_loss_roe": 0.02,
            "take_profit_roe": None,
        }
    ]


@pytest.mark.asyncio
async def test_order_queue_worker_updates_only_take_profit_intent_on_update_tp():
    idea = ExecutionIdea(
        action=ExecutionAction.UPDATE_TP,
        symbol="BTC",
        take_profit_roe=0.05,
    ).to_dict()
    position_origin_service = StubPositionOriginService()
    worker = _build_worker(
        _build_item(idea),
        ExecutionResult(success=True, status="filled", order_id="1"),
        position_origin_service,
    )

    handled = await worker.process_next()

    assert handled is True
    assert position_origin_service.upserts == [
        {
            "account_id": "acc-1",
            "symbol": "BTC",
            "anchor_frame": None,
            "active_tunnel": None,
            "stop_loss_roe": None,
            "take_profit_roe": 0.05,
        }
    ]


@pytest.mark.asyncio
async def test_order_queue_worker_registers_auto_add_for_fresh_filled_market_open():
    idea = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG,
        symbol="BTC",
        position_size_usd=100,
        leverage=5,
        stop_loss_roe=0.03,
        take_profit_roe=0.08,
    ).to_dict()
    pending_entry_service = StubPendingEntryService()
    position_origin_service = StubPositionOriginService()
    auto_add_service = StubAutoAddService()
    worker = _build_worker_with_pending(
        _build_item(idea),
        ExecutionResult(
            success=True,
            status="filled",
            order_id="mkt-auto-add-1",
            fill_price=100.0,
            filled_size=1.0,
        ),
        position_origin_service,
        pending_entry_service,
        auto_add_service=auto_add_service,
    )

    handled = await worker.process_next()

    assert handled is True
    assert len(auto_add_service.register_calls) == 1
    call = auto_add_service.register_calls[0]
    assert call["decision"].action == ExecutionAction.OPEN_LONG
    assert call["session_id"] == "session-1"
    assert call["open_positions_before"] == []


@pytest.mark.asyncio
async def test_order_queue_worker_retries_limit_open_three_times_before_success():
    idea = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG_LIMIT,
        symbol="BTC",
        position_size_usd=100,
        limit_price=100,
        anchor_frame="2h",
        active_tunnel="slow",
    ).to_dict()
    pending_entry_service = StubPendingEntryService()
    position_origin_service = StubPositionOriginService()
    worker = _build_worker_with_pending(
        _build_item(idea),
        [
            ExecutionResult(success=False, status="error", error="temporary_exchange_error_1"),
            ExecutionResult(success=False, status="error", error="temporary_exchange_error_2"),
            ExecutionResult(success=True, status="resting", order_id="limit-1"),
        ],
        position_origin_service,
        pending_entry_service,
    )

    handled = await worker.process_next()

    assert handled is True
    assert worker._repository.done_result is not None
    assert worker._repository.failed_error is None
    assert worker._repository.done_result[1]["retry_attempts"] == 3
    assert worker._repository.done_result[1]["retry_errors"] == [
        "temporary_exchange_error_1",
        "temporary_exchange_error_2",
    ]
    assert len(worker._trade_executor.calls) == 3
    assert len(pending_entry_service.resting_calls) == 1

    trade_executed = _event_payload(worker._outbox.events, topics.TRADE_EXECUTED)
    assert trade_executed["retry_attempts"] == 3
    assert trade_executed["retried"] is True
    assert trade_executed["retry_errors"] == [
        "temporary_exchange_error_1",
        "temporary_exchange_error_2",
    ]


@pytest.mark.asyncio
async def test_order_queue_worker_marks_failed_after_three_limit_open_failures_with_retry_metadata():
    idea = ExecutionIdea(
        action=ExecutionAction.OPEN_SHORT_LIMIT,
        symbol="BTC",
        position_size_usd=100,
        limit_price=100,
    ).to_dict()
    pending_entry_service = StubPendingEntryService()
    position_origin_service = StubPositionOriginService()
    worker = _build_worker_with_pending(
        _build_item(idea),
        [
            ExecutionResult(success=False, status="error", error="temporary_exchange_error_1"),
            ExecutionResult(success=False, status="error", error="temporary_exchange_error_2"),
            ExecutionResult(success=False, status="error", error="temporary_exchange_error_3"),
        ],
        position_origin_service,
        pending_entry_service,
    )

    handled = await worker.process_next()

    assert handled is True
    assert worker._repository.done_result is None
    assert worker._repository.failed_error == ("ord-1", "temporary_exchange_error_3")
    assert len(worker._trade_executor.calls) == 3
    assert pending_entry_service.resting_calls == []

    trade_failed = _event_payload(worker._outbox.events, topics.TRADE_FAILED)
    assert trade_failed["retry_attempts"] == 3
    assert trade_failed["retried"] is True
    assert trade_failed["retry_errors"] == [
        "temporary_exchange_error_1",
        "temporary_exchange_error_2",
        "temporary_exchange_error_3",
    ]


@pytest.mark.asyncio
async def test_order_queue_worker_cancels_stale_entry_orders_before_limit_open():
    idea = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG_LIMIT,
        symbol="BTC",
        position_size_usd=100,
        limit_price=100,
    ).to_dict()
    pending_entry_service = StubPendingEntryService()
    pending_entry_service.active_records = [
        type(
            "PendingEntryRecord",
            (),
            {
                "id": "pe-1",
                "symbol": "BTC",
                "side": "LONG",
                "status": type("Status", (), {"value": "RESTING"})(),
                "exchange_order_id": "old-limit-1",
            },
        )()
    ]
    position_origin_service = StubPositionOriginService()
    portfolio_service = StubPortfolioService()
    portfolio_service.open_orders = [
        {"id": "old-limit-1", "symbol": "BTC/USDT:USDT", "type": "limit"},
        {
            "id": "keep-protection",
            "symbol": "BTC/USDT:USDT",
            "type": "take_profit_market",
            "closePosition": True,
            "stopPrice": 110.0,
        },
    ]
    worker = _build_worker_with_pending(
        _build_item(idea),
        ExecutionResult(success=True, status="resting", order_id="new-limit-1"),
        position_origin_service,
        pending_entry_service,
        portfolio_service=portfolio_service,
    )

    handled = await worker.process_next()

    assert handled is True
    assert portfolio_service.canceled_orders == [("old-limit-1", "BTC/USDT:USDT")]
    assert pending_entry_service.cancel_calls == ["pe-1"]
    assert len(worker._trade_executor.calls) == 1
    cleanup_event = next(
        payload
        for topic, payload in worker._outbox.events
        if topic == topics.ORDER_MODIFIED and payload.get("execution_cleanup")
    )
    assert cleanup_event["execution_cleanup"]["canceled_entry_orders"] == [
        {
            "order_id": "old-limit-1",
            "symbol": "BTC/USDT:USDT",
            "type": "limit",
        }
    ]
    assert cleanup_event["execution_cleanup"]["canceled_pending_entries"] == ["pe-1"]


@pytest.mark.asyncio
async def test_order_queue_worker_does_not_retry_market_open_failures():
    idea = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG,
        symbol="BTC",
        position_size_usd=100,
    ).to_dict()
    pending_entry_service = StubPendingEntryService()
    position_origin_service = StubPositionOriginService()
    worker = _build_worker_with_pending(
        _build_item(idea),
        [
            ExecutionResult(success=False, status="error", error="market_open_failed_once"),
            ExecutionResult(success=True, status="filled", order_id="should-not-run"),
        ],
        position_origin_service,
        pending_entry_service,
    )

    handled = await worker.process_next()

    assert handled is True
    assert worker._repository.done_result is None
    assert worker._repository.failed_error == ("ord-1", "market_open_failed_once")
    assert len(worker._trade_executor.calls) == 1


@pytest.mark.asyncio
async def test_order_queue_worker_rejects_market_open_when_inflight_reservations_exceed_max_positions():
    OrderQueueWorker._market_open_reservations = {
        "acc-1": {
            "other-request": type(
                "Reservation",
                (),
                {
                    "symbol": "BTC",
                    "expires_at": datetime.now(timezone.utc) + timedelta(seconds=30),
                },
            )(),
        }
    }

    idea = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG,
        symbol="ETH",
        position_size_usd=100,
    ).to_dict()
    pending_entry_service = StubPendingEntryService()
    position_origin_service = StubPositionOriginService()
    trade_guard = StubMarketCapTradeGuard()
    worker = _build_worker_with_pending(
        _build_item(idea),
        ExecutionResult(success=True, status="filled", order_id="should-not-run"),
        position_origin_service,
        pending_entry_service,
        trade_guard=trade_guard,
        automation_config_service=StubAutomationConfigService(max_positions=1),
    )

    handled = await worker.process_next()

    assert handled is True
    assert worker._repository.done_result is None
    assert worker._repository.failed_error == ("ord-1", "trade_guard_rejected")
    assert len(worker._trade_executor.calls) == 0
    assert trade_guard.calls[0]["max_positions"] == 1
    assert trade_guard.calls[0]["inflight_market_open_count"] == 2
    assert "src-1" not in OrderQueueWorker._market_open_reservations.get("acc-1", {})

    OrderQueueWorker._market_open_reservations = {}


@pytest.mark.asyncio
async def test_order_queue_worker_blocks_limit_open_when_entry_slots_full():
    OrderQueueWorker._limit_entry_reservations = {}

    idea = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG_LIMIT,
        symbol="XRP",
        position_size_usd=100,
        limit_price=1.0,
    ).to_dict()
    pending_entry_service = StubPendingEntryService()
    pending_entry_service.active_records = [
        type(
            "PendingEntryRecord",
            (),
            {
                "id": "pe-eth",
                "symbol": "ETH",
                "side": "LONG",
                "status": type("Status", (), {"value": "RESTING"})(),
                "exchange_order_id": "limit-eth-1",
            },
        )()
    ]
    position_origin_service = StubPositionOriginService()
    portfolio_service = StubPortfolioService()
    portfolio_service.snapshot_class = StubPortfolioSnapshotWithPosition
    worker = _build_worker_with_pending(
        _build_item(idea),
        ExecutionResult(success=True, status="resting", order_id="should-not-run"),
        position_origin_service,
        pending_entry_service,
        portfolio_service=portfolio_service,
        automation_config_service=StubAutomationConfigService(max_positions=1),
    )

    handled = await worker.process_next()

    assert handled is True
    assert worker._repository.done_result is None
    assert worker._repository.failed_error == ("ord-1", "limit_entry_slot_cap_reached: used=2 limit=2")
    assert len(worker._trade_executor.calls) == 0
    trade_failed = _event_payload(worker._outbox.events, topics.TRADE_FAILED)
    assert trade_failed["result"]["raw_response"] == {
        "slot_limit": 2,
        "slots_used": 2,
        "open_positions": 1,
        "pending_entries": 1,
        "inflight_limit_entries": 0,
    }


@pytest.mark.asyncio
async def test_order_queue_worker_counts_inflight_limit_reservations_against_slot_cap():
    OrderQueueWorker._limit_entry_reservations = {
        "acc-1": {
            "other-request": type(
                "Reservation",
                (),
                {"expires_at": datetime.now(timezone.utc).replace(microsecond=0)},
            )(),
        }
    }
    OrderQueueWorker._limit_entry_reservations["acc-1"]["other-request"].expires_at = datetime.now(
        timezone.utc
    ) + timedelta(seconds=30)

    idea = ExecutionIdea(
        action=ExecutionAction.OPEN_SHORT_LIMIT,
        symbol="SOL",
        position_size_usd=100,
        limit_price=120.0,
    ).to_dict()
    pending_entry_service = StubPendingEntryService()
    position_origin_service = StubPositionOriginService()
    portfolio_service = StubPortfolioService()
    portfolio_service.snapshot_class = StubPortfolioSnapshotWithPosition
    worker = _build_worker_with_pending(
        _build_item(idea),
        ExecutionResult(success=True, status="resting", order_id="should-not-run"),
        position_origin_service,
        pending_entry_service,
        portfolio_service=portfolio_service,
        automation_config_service=StubAutomationConfigService(max_positions=1),
    )

    handled = await worker.process_next()

    assert handled is True
    assert worker._repository.done_result is None
    assert worker._repository.failed_error == ("ord-1", "limit_entry_slot_cap_reached: used=2 limit=2")
    assert len(worker._trade_executor.calls) == 0
    OrderQueueWorker._limit_entry_reservations = {}


@pytest.mark.asyncio
async def test_order_queue_worker_frees_same_symbol_pending_slot_before_limit_gate():
    OrderQueueWorker._limit_entry_reservations = {}

    idea = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG_LIMIT,
        symbol="BTC",
        position_size_usd=100,
        limit_price=100,
    ).to_dict()
    pending_entry_service = StubPendingEntryService()
    pending_entry_service.active_records = [
        type(
            "PendingEntryRecord",
            (),
            {
                "id": "pe-btc",
                "symbol": "BTC",
                "side": "LONG",
                "status": type("Status", (), {"value": "RESTING"})(),
                "exchange_order_id": "old-limit-1",
            },
        )(),
        type(
            "PendingEntryRecord",
            (),
            {
                "id": "pe-eth",
                "symbol": "ETH",
                "side": "LONG",
                "status": type("Status", (), {"value": "RESTING"})(),
                "exchange_order_id": "eth-limit-1",
            },
        )(),
    ]
    position_origin_service = StubPositionOriginService()
    portfolio_service = StubPortfolioService()
    portfolio_service.open_orders = [
        {"id": "old-limit-1", "symbol": "BTC/USDT:USDT", "type": "limit"},
    ]
    worker = _build_worker_with_pending(
        _build_item(idea),
        ExecutionResult(success=True, status="resting", order_id="new-limit-1"),
        position_origin_service,
        pending_entry_service,
        portfolio_service=portfolio_service,
        automation_config_service=StubAutomationConfigService(max_positions=1),
    )

    handled = await worker.process_next()

    assert handled is True
    assert worker._repository.failed_error is None
    assert worker._repository.done_result is not None
    assert len(worker._trade_executor.calls) == 1
    assert pending_entry_service.cancel_calls == ["pe-btc"]
