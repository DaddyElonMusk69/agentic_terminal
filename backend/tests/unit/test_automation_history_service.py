from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.application.automation import topics
from app.application.automation.history_service import (
    AutomationHistoryService,
    _build_trade_payload,
)
from app.domain.automation_history.models import AutomationSessionRecord, AutomationTradeRecord


class DummySessionRepo:
    def __init__(self, session: AutomationSessionRecord | None = None) -> None:
        self._session = session

    async def get_by_id(self, session_id: str):
        if self._session and self._session.id == session_id:
            return self._session
        return None

    async def create_session(self, **kwargs):
        raise NotImplementedError

    async def list_all(self, limit: int, offset: int):
        return []

    async def count_all(self):
        return 0

    async def end_session(self, **kwargs):
        return None

    async def increment_prompt_count(self, session_id: str, delta: int = 1):
        return None

    async def delete_session(self, session_id: str):
        return False


class DummyLogRepo:
    async def create_log(self, **kwargs):
        return None

    async def list_by_session(self, session_id: str, limit: int, offset: int):
        return []

    async def delete_by_session(self, session_id: str):
        return 0


class DummyTradeRepo:
    def __init__(
        self,
        session_trades: list[AutomationTradeRecord] | None = None,
        order_ids: set[str] | None = None,
    ) -> None:
        self._session_trades = list(session_trades or [])
        self._order_ids = set(order_ids or {"external:existing"})
        self.created: list[dict] = []
        self.updated: list[dict] = []

    async def create_trade(self, session_id: str, **kwargs):
        self.created.append({"session_id": session_id, **kwargs})
        order_id = kwargs.get("order_id")
        if isinstance(order_id, str) and order_id.strip():
            self._order_ids.add(order_id)
        return None

    async def list_by_session(self, session_id: str):
        return [trade for trade in self._session_trades if trade.session_id == session_id]

    async def list_order_ids_by_session(self, session_id: str):
        return set(self._order_ids)

    async def update_trade(self, trade_id: int, updates: dict):
        for index, trade in enumerate(self._session_trades):
            if trade.id != trade_id:
                continue
            updated = replace(trade, **updates)
            self._session_trades[index] = updated
            self.updated.append({"id": trade_id, "updates": dict(updates)})
            order_id = updates.get("order_id")
            if isinstance(order_id, str) and order_id.strip():
                self._order_ids.add(order_id)
            return updated
        return None

    async def count_by_session(self, session_id: str):
        return 0

    async def sum_pnl_by_session(self, session_id: str):
        return 0.0

    async def delete_by_session(self, session_id: str):
        return 0


def _make_session(
    session_id: str = "session-1",
    started_at: datetime | None = None,
) -> AutomationSessionRecord:
    return AutomationSessionRecord(
        id=session_id,
        started_at=started_at or datetime.now(timezone.utc),
        ended_at=None,
        execution_mode="production",
        provider="codex",
        model="gpt-5.3-codex",
        total_cycles=0,
        total_trades=0,
        total_pnl=0.0,
        prompt_count=0,
        config_snapshot=None,
    )


def _make_trade(
    *,
    trade_id: int,
    session_id: str = "session-1",
    created_at: datetime | None = None,
    symbol: str = "BTC",
    action: str = "CLOSE",
    order_id: str | None = None,
    pnl: float | None = None,
    exit_price: float | None = None,
    fill_price: float | None = None,
    closed_at: datetime | None = None,
) -> AutomationTradeRecord:
    return AutomationTradeRecord(
        id=trade_id,
        session_id=session_id,
        created_at=created_at or datetime.now(timezone.utc),
        cycle_number=3,
        symbol=symbol,
        direction="LONG",
        action=action,
        entry_price=None,
        exit_price=exit_price,
        size_usd=100.0,
        pnl=pnl,
        pnl_pct=None,
        status="filled",
        closed_at=closed_at,
        signal_data=None,
        llm_reasoning="test",
        llm_response_full=None,
        order_id=order_id,
        fill_price=fill_price,
    )


def test_build_trade_payload_prefers_realized_pnl_even_if_zero():
    payload = {
        "execution_idea": {"symbol": "BTC", "action": "CLOSE"},
        "result": {
            "status": "filled",
            "realized_pnl": 0.0,
            "pnl": 15.5,
            "fill_price": 100.0,
        },
    }

    trade = _build_trade_payload(topics.TRADE_EXECUTED, payload)

    assert trade is not None
    assert trade["pnl"] == 0.0


@pytest.mark.asyncio
async def test_sync_external_trades_dedupes_by_order_id_and_sets_closed_at():
    trade_repo = DummyTradeRepo()
    service = AutomationHistoryService(
        session_repo=DummySessionRepo(),
        log_repo=DummyLogRepo(),
        trade_repo=trade_repo,
    )

    synced = await service.sync_external_trades(
        session_id="session-1",
        cycle_number=3,
        trades=[
            {
                "symbol": "BTCUSDT",
                "order_id": "existing",
                "pnl": 12.5,
                "exit_time": int(datetime.now(timezone.utc).timestamp() * 1000),
            },
            {
                "symbol": "ETHUSDT",
                "order_id": "new-one",
                "direction": "long",
                "entry_price": 2500,
                "exit_price": 2550,
                "pnl": 23.2,
                "roi_pct": 1.1,
                "exit_time": int(datetime.now(timezone.utc).timestamp() * 1000),
            },
        ],
    )

    assert synced == 1
    assert len(trade_repo.created) == 1
    created = trade_repo.created[0]
    assert created["symbol"] == "ETH"
    assert created["order_id"] == "external:new-one"
    assert created["pnl"] == 23.2
    assert created["pnl_pct"] == 1.1
    assert created["direction"] == "LONG"
    assert created["cycle_number"] == 3
    assert created["closed_at"] is not None


@pytest.mark.asyncio
async def test_reconcile_external_trades_updates_existing_close_by_order_id():
    now = datetime.now(timezone.utc)
    session = _make_session(started_at=now - timedelta(hours=1))
    local_trade = _make_trade(
        trade_id=101,
        symbol="ETH",
        action="CLOSE",
        order_id="991122",
        created_at=now - timedelta(minutes=5),
        pnl=None,
        closed_at=None,
    )
    trade_repo = DummyTradeRepo(session_trades=[local_trade], order_ids={"991122"})
    service = AutomationHistoryService(
        session_repo=DummySessionRepo(session=session),
        log_repo=DummyLogRepo(),
        trade_repo=trade_repo,
    )

    summary = await service.reconcile_external_trades(
        session_id="session-1",
        cycle_number=7,
        started_at=session.started_at - timedelta(minutes=5),
        ended_at=now + timedelta(minutes=5),
        trades=[
            {
                "symbol": "ETHUSDT",
                "order_id": "991122",
                "direction": "long",
                "entry_price": 2450,
                "exit_price": 2490,
                "pnl": 18.75,
                "roi_pct": 1.5,
                "exit_time": int(now.timestamp() * 1000),
            }
        ],
    )

    assert summary["scanned"] == 1
    assert summary["in_window"] == 1
    assert summary["matched"] == 1
    assert summary["updated"] == 1
    assert summary["created"] == 0
    assert trade_repo.created == []
    assert len(trade_repo.updated) == 1
    updates = trade_repo.updated[0]["updates"]
    assert updates["pnl"] == 18.75
    assert updates["pnl_pct"] == 1.5
    assert updates["exit_price"] == 2490.0
    assert updates["fill_price"] == 2490.0
    assert updates["closed_at"] is not None


@pytest.mark.asyncio
async def test_reconcile_external_trades_matches_by_symbol_time_when_order_id_differs():
    now = datetime.now(timezone.utc)
    session = _make_session(started_at=now - timedelta(hours=2))
    local_trade = _make_trade(
        trade_id=301,
        symbol="PAXG",
        action="CLOSE",
        order_id="3202044905",
        created_at=now - timedelta(seconds=20),
        pnl=None,
        closed_at=None,
    )
    trade_repo = DummyTradeRepo(session_trades=[local_trade], order_ids={"3202044905"})
    service = AutomationHistoryService(
        session_repo=DummySessionRepo(session=session),
        log_repo=DummyLogRepo(),
        trade_repo=trade_repo,
    )

    summary = await service.reconcile_external_trades(
        session_id="session-1",
        cycle_number=9,
        started_at=session.started_at - timedelta(minutes=5),
        ended_at=now + timedelta(minutes=5),
        trades=[
            {
                "symbol": "PAXGUSDT",
                "order_id": "trade-abc-1",
                "direction": "short",
                "entry_price": 5200,
                "exit_price": 5209.9,
                "pnl": -0.0393,
                "roi_pct": -0.5,
                "exit_time": int((now - timedelta(seconds=5)).timestamp() * 1000),
            }
        ],
    )

    assert summary["matched"] == 1
    assert summary["updated"] == 1
    assert summary["created"] == 0
    assert trade_repo.created == []
    assert len(trade_repo.updated) == 1
    assert trade_repo.updated[0]["updates"]["pnl"] == -0.0393


@pytest.mark.asyncio
async def test_reconcile_external_trades_creates_unmatched_close_sync_in_window():
    now = datetime.now(timezone.utc)
    session = _make_session(started_at=now - timedelta(hours=1))
    trade_repo = DummyTradeRepo(session_trades=[], order_ids=set())
    service = AutomationHistoryService(
        session_repo=DummySessionRepo(session=session),
        log_repo=DummyLogRepo(),
        trade_repo=trade_repo,
    )

    summary = await service.reconcile_external_trades(
        session_id="session-1",
        cycle_number=2,
        started_at=session.started_at - timedelta(minutes=5),
        ended_at=now + timedelta(minutes=5),
        trades=[
            {
                "symbol": "SOLUSDT",
                "order_id": "new-sync-order",
                "direction": "long",
                "entry_price": 100,
                "exit_price": 102,
                "pnl": 6.0,
                "roi_pct": 2.0,
                "exit_time": int(now.timestamp() * 1000),
            }
        ],
    )

    assert summary["matched"] == 0
    assert summary["updated"] == 0
    assert summary["created"] == 1
    assert len(trade_repo.created) == 1
    created = trade_repo.created[0]
    assert created["action"] == "CLOSE_SYNC"
    assert created["symbol"] == "SOL"
    assert created["order_id"] == "external:new-sync-order"


@pytest.mark.asyncio
async def test_reconcile_external_trades_ignores_out_of_window_records():
    now = datetime.now(timezone.utc)
    session = _make_session(started_at=now - timedelta(hours=1))
    trade_repo = DummyTradeRepo(session_trades=[], order_ids=set())
    service = AutomationHistoryService(
        session_repo=DummySessionRepo(session=session),
        log_repo=DummyLogRepo(),
        trade_repo=trade_repo,
    )

    summary = await service.reconcile_external_trades(
        session_id="session-1",
        cycle_number=2,
        started_at=session.started_at,
        ended_at=now,
        trades=[
            {
                "symbol": "SOLUSDT",
                "order_id": "old-order",
                "direction": "long",
                "entry_price": 100,
                "exit_price": 102,
                "pnl": 6.0,
                "roi_pct": 2.0,
                "exit_time": int((session.started_at - timedelta(hours=2)).timestamp() * 1000),
            }
        ],
    )

    assert summary["scanned"] == 1
    assert summary["in_window"] == 0
    assert summary["created"] == 0
    assert trade_repo.created == []
