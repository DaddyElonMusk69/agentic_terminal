from unittest.mock import AsyncMock

import pytest

from app.domain.llm_response_worker.models import ExecutionAction, ExecutionIdea
from app.domain.trade_executor.models import ExecutionResult
from app.infrastructure.exchange.ccxt_trade_executor import (
    CCXTTradeConfig,
    CCXTTradeExecutor,
    ProtectionOrderSnapshot,
    _calculate_initial_stop_loss_from_roe,
    _merge_entry_execution_with_protection,
)


def test_initial_stop_loss_from_roe_uses_loss_side_for_long_entries():
    assert _calculate_initial_stop_loss_from_roe(
        risk_roe=0.03,
        entry_price=101.0,
        leverage=5.0,
        direction="long",
    ) == 100.39


def test_initial_stop_loss_from_roe_uses_loss_side_for_short_entries():
    assert _calculate_initial_stop_loss_from_roe(
        risk_roe=0.03,
        entry_price=101.0,
        leverage=5.0,
        direction="short",
    ) == 101.61


def test_entry_execution_keeps_success_but_surfaces_protection_failure():
    entry = ExecutionResult(
        success=True,
        status="filled",
        order_id="entry-1",
        fill_price=101.0,
        filled_size=1.0,
        raw_response={"id": "entry-1"},
    )
    protection = ExecutionResult(
        success=False,
        status="failed",
        error="No open position for BTC/USDT:USDT",
        raw_response={"stage": "sl"},
    )

    merged = _merge_entry_execution_with_protection(entry, protection)

    assert merged.success is True
    assert merged.status == "filled"
    assert merged.order_id == "entry-1"
    assert merged.error == "protection_attach_failed: No open position for BTC/USDT:USDT"


def _make_executor() -> CCXTTradeExecutor:
    executor = object.__new__(CCXTTradeExecutor)
    executor._config = CCXTTradeConfig(
        exchange_id="binance",
        api_key="key",
        api_secret="secret",
        passphrase=None,
        is_testnet=True,
    )
    executor._client = type("ClientStub", (), {})()
    return executor


@pytest.mark.asyncio
async def test_update_take_profit_restores_previous_order_on_replace_failure():
    executor = _make_executor()
    executor._load_position_context = AsyncMock(
        return_value=CCXTTradeExecutor._PositionContext(
            position={"side": "long", "contracts": 1.0},
            side="sell",
            amount=1.0,
            error_result=None,
        )
    )
    executor._get_existing_protection_order = AsyncMock(
        return_value=ProtectionOrderSnapshot(trigger_price=110.0, order_type="take_profit")
    )
    executor._cancel_conditional_orders = AsyncMock(return_value=ExecutionResult(success=True, status="canceled"))
    executor._place_protection_order = AsyncMock(
        side_effect=[
            ExecutionResult(success=False, status="error", error="create failed", raw_response={"stage": "new"}),
            ExecutionResult(success=True, status="tp_set", order_id="restore-tp", raw_response={"id": "restore-tp"}),
        ]
    )

    result = await executor._update_take_profit("BTC/USDT:USDT", 120.0)

    assert result.success is False
    assert result.status == "rolled_back"
    assert "restored previous take profit at 110" in (result.error or "")

    place_calls = executor._place_protection_order.await_args_list
    assert len(place_calls) == 2
    assert place_calls[0].kwargs["order_type"] == "take_profit_market"
    assert place_calls[0].kwargs["trigger_price"] == 120.0
    assert place_calls[1].kwargs["order_type"] == "take_profit"
    assert place_calls[1].kwargs["trigger_price"] == 110.0


@pytest.mark.asyncio
async def test_update_stop_loss_restores_previous_order_on_replace_failure():
    executor = _make_executor()
    executor._load_position_context = AsyncMock(
        return_value=CCXTTradeExecutor._PositionContext(
            position={"side": "short", "contracts": 2.0},
            side="buy",
            amount=2.0,
            error_result=None,
        )
    )
    executor._get_existing_protection_order = AsyncMock(
        return_value=ProtectionOrderSnapshot(trigger_price=101.5, order_type="stop")
    )
    executor._cancel_conditional_orders = AsyncMock(return_value=ExecutionResult(success=True, status="canceled"))
    executor._place_protection_order = AsyncMock(
        side_effect=[
            ExecutionResult(success=False, status="error", error="create failed", raw_response={"stage": "new"}),
            ExecutionResult(success=True, status="sl_set", order_id="restore-sl", raw_response={"id": "restore-sl"}),
        ]
    )

    result = await executor._update_stop_loss("BTC/USDT:USDT", 100.0)

    assert result.success is False
    assert result.status == "rolled_back"
    assert "restored previous stop loss at 101.5" in (result.error or "")

    place_calls = executor._place_protection_order.await_args_list
    assert len(place_calls) == 2
    assert place_calls[0].kwargs["order_type"] == "stop_market"
    assert place_calls[0].kwargs["trigger_price"] == 100.0
    assert place_calls[1].kwargs["order_type"] == "stop"
    assert place_calls[1].kwargs["trigger_price"] == 101.5


@pytest.mark.asyncio
async def test_open_position_does_not_touch_protection_when_already_in_position():
    executor = _make_executor()
    executor._has_open_position = AsyncMock(return_value=True)
    executor._set_margin_mode = AsyncMock()
    executor._client.set_leverage = AsyncMock()
    executor._client.fetch_ticker = AsyncMock(return_value={"last": 100.0})
    executor._create_order_with_reduce_only_fallback = AsyncMock(
        return_value={"id": "entry-add", "average": 100.0, "filled": 1.0}
    )
    executor._maybe_set_sl_tp = AsyncMock(
        return_value=ExecutionResult(success=True, status="sl_tp_set", order_id="protect-1")
    )

    decision = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG,
        symbol="BTC",
        position_size_usd=100.0,
        leverage=5,
        stop_loss_roe=0.03,
        take_profit_roe=0.05,
    )

    result = await executor._open_position("BTC/USDT:USDT", "buy", 100.0, 5, decision)

    assert result.success is True
    assert result.status == "filled"
    executor._maybe_set_sl_tp.assert_not_awaited()


@pytest.mark.asyncio
async def test_open_position_sets_initial_protection_for_fresh_entry():
    executor = _make_executor()
    executor._has_open_position = AsyncMock(return_value=False)
    executor._set_margin_mode = AsyncMock()
    executor._client.set_leverage = AsyncMock()
    executor._client.fetch_ticker = AsyncMock(return_value={"last": 100.0})
    executor._create_order_with_reduce_only_fallback = AsyncMock(
        return_value={"id": "entry-fresh", "average": 100.0, "filled": 1.0}
    )
    executor._maybe_set_sl_tp = AsyncMock(
        return_value=ExecutionResult(success=True, status="sl_tp_set", order_id="protect-1")
    )

    decision = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG,
        symbol="BTC",
        position_size_usd=100.0,
        leverage=5,
        stop_loss_roe=0.03,
        take_profit_roe=0.05,
    )

    result = await executor._open_position("BTC/USDT:USDT", "buy", 100.0, 5, decision)

    assert result.success is True
    assert result.status == "filled"
    executor._maybe_set_sl_tp.assert_awaited_once()


@pytest.mark.asyncio
async def test_maybe_set_sl_tp_prefers_explicit_initial_prices_over_roe_recalculation():
    executor = _make_executor()
    executor.set_sl_tp = AsyncMock(return_value=ExecutionResult(success=True, status="sl_tp_set"))

    decision = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG,
        symbol="BTC",
        leverage=5,
        stop_loss=99.0,
        take_profit=104.0,
        stop_loss_roe=0.03,
        take_profit_roe=0.08,
    )
    result = ExecutionResult(
        success=True,
        status="filled",
        fill_price=101.0,
        filled_size=1.0,
    )

    protection = await executor._maybe_set_sl_tp("BTC/USDT:USDT", decision, result)

    assert protection is not None
    executor.set_sl_tp.assert_awaited_once_with("BTC/USDT:USDT", 99.0, 104.0)


@pytest.mark.asyncio
async def test_place_protection_order_uses_close_position_trigger_orders():
    executor = _make_executor()
    executor._client.create_order = AsyncMock(return_value={"id": "tp-1"})

    result = await executor._place_protection_order(
        symbol="BTC/USDT:USDT",
        position={"side": "long", "contracts": 1.0, "info": {"positionSide": "LONG"}},
        side="sell",
        order_type="take_profit_market",
        trigger_price=110.0,
        success_status="tp_set",
    )

    assert result.success is True
    executor._client.create_order.assert_awaited_once_with(
        symbol="BTC/USDT:USDT",
        type="take_profit_market",
        side="sell",
        amount=None,
        price=None,
        params={
            "closePosition": True,
            "stopPrice": 110.0,
            "positionSide": "LONG",
        },
    )
