from datetime import datetime, timezone

import pytest

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


class StubCircuitBreaker:
    def evaluate(self, decision):  # noqa: ANN001
        return CircuitBreakerResult(allowed=True, decision=decision)


class StubTradeExecutor:
    def __init__(self, result: ExecutionResult) -> None:
        self._result = result

    async def execute(self, decision):  # noqa: ANN001
        return self._result


class StubOutbox:
    async def enqueue_event(self, topic: str, payload: dict):  # noqa: ANN001
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


class StubPortfolioService:
    async def get_portfolio_snapshot(self):
        return StubPortfolioSnapshot()

    async def get_open_orders(self, symbols=None):  # noqa: ANN001
        return []

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

    async def upsert(self, account_id: str, symbol, anchor_frame, active_tunnel):  # noqa: ANN001
        self.upserts.append(
            {
                "account_id": account_id,
                "symbol": symbol,
                "anchor_frame": anchor_frame,
                "active_tunnel": active_tunnel,
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
    worker = _build_worker(
        _build_item(idea),
        ExecutionResult(success=True, status="filled", order_id="1", fill_price=100.0),
        position_origin_service,
    )

    handled = await worker.process_next()

    assert handled is True
    assert position_origin_service.upserts == []
    assert position_origin_service.deletes == [{"account_id": "acc-1", "symbol": "BTC"}]


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
    assert position_origin_service.deletes == []
