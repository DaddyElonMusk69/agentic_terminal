#!/usr/bin/env python3
"""
CCXT Trade Executor Test Script

Tests the backend CCXTTradeExecutor (backend/src) for basic order execution.
Run with: python test_ccxt_executor.py

IMPORTANT: Fill in credentials below before running.
"""

import asyncio
import re
import sys
from typing import Any, Dict, Optional

# Prefer backend package over root-level app/
sys.path.insert(0, "backend/src")

from app.infrastructure.exchange.ccxt_trade_executor import CCXTTradeConfig, CCXTTradeExecutor
from app.domain.llm_response_worker.models import ExecutionAction, ExecutionIdea

# =============================================================================
# CONFIGURATION - Fill these in!
# =============================================================================

# Exchange config
EXCHANGE_ID = "binance"  # e.g. "binance", "okx"
API_KEY = "ryoQuW77zRoRuXCWmeZwF3pOSvBywvEzqDfDj2OFUR2O9yRl3WP33BhLM3goj0Tj"
API_SECRET = "TT4RexZZImYZkjo2WMMDRdvTc9ifX2kk3WoiGs0t3R8tdYGHJ7D1n7XaFCJL6QIy"
PASSPHRASE = ""  # OKX only
IS_TESTNET = False
QUOTE_ASSET = "USDT"

# Test settings
TEST_SYMBOL = "SOL"  # Symbol to test with
TEST_SIZE_USD = 11.0
TEST_LEVERAGE = 1
DEBUG_CCXT_REQUESTS = True


def _float_or_none(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _position_size(pos: Dict[str, Any]) -> float:
    for key in ("contracts", "size", "positionAmt"):
        val = _float_or_none(pos.get(key))
        if val is not None:
            return abs(val)
    return 0.0


def _position_side(pos: Dict[str, Any]) -> str:
    side = pos.get("side")
    if side:
        return str(side).lower()
    info = pos.get("info", {})
    if isinstance(info, dict):
        for key in ("positionSide", "side", "posSide"):
            val = info.get(key)
            if val:
                return str(val).lower()
    amt = _float_or_none(pos.get("positionAmt"))
    if amt is not None:
        return "short" if amt < 0 else "long"
    return "unknown"


def _position_entry_price(pos: Dict[str, Any]) -> Optional[float]:
    for key in ("entryPrice", "avgPrice", "average"):
        val = _float_or_none(pos.get(key))
        if val is not None and val > 0:
            return val
    return None


def _redact_signature(value: Optional[str]) -> Optional[str]:
    if not value:
        return value
    return re.sub(r"(signature=)[^&\\s]+", r"\\1REDACTED", value)


def _print_last_ccxt_request(executor: CCXTTradeExecutor, label: str) -> None:
    if not DEBUG_CCXT_REQUESTS:
        return
    url = getattr(executor._client, "last_request_url", None)
    body = getattr(executor._client, "last_request_body", None)
    if url:
        print(f"\n[CCXT] {label} - last_request_url:")
        print(_redact_signature(str(url)))
    if body:
        print(f"\n[CCXT] {label} - last_request_body:")
        print(_redact_signature(str(body)))


def _extract_order_type(order: Dict[str, Any]) -> str:
    raw = order.get("type")
    if not raw:
        info = order.get("info") or {}
        if isinstance(info, dict):
            raw = info.get("type") or info.get("orderType")
    return str(raw or "").lower()


def _extract_stop_price(order: Dict[str, Any]) -> Optional[float]:
    for key in ("stopPrice", "triggerPrice"):
        value = _float_or_none(order.get(key))
        if value and value > 0:
            return value
    info = order.get("info") or {}
    if isinstance(info, dict):
        for key in ("stopPrice", "triggerPrice", "triggerPx"):
            value = _float_or_none(info.get(key))
            if value and value > 0:
                return value
    return None


def _extract_reduce_only(order: Dict[str, Any]) -> bool:
    value = order.get("reduceOnly")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "true"
    close_position = order.get("closePosition")
    if isinstance(close_position, bool):
        return close_position
    if isinstance(close_position, str):
        return close_position.lower() == "true"
    info = order.get("info") or {}
    if isinstance(info, dict):
        info_value = info.get("reduceOnly")
        if isinstance(info_value, bool):
            return info_value
        if isinstance(info_value, str):
            return info_value.lower() == "true"
        close_info = info.get("closePosition")
        if isinstance(close_info, bool):
            return close_info
        if isinstance(close_info, str):
            return close_info.lower() == "true"
    return False


def _is_trigger_order(order_type: str, stop_price: Optional[float], reduce_only: bool) -> bool:
    if stop_price is not None:
        return True
    if "stop" in order_type or "profit" in order_type:
        return True
    return reduce_only


async def _fetch_ticker(executor: CCXTTradeExecutor, symbol: str) -> Optional[float]:
    try:
        ticker = await executor._client.fetch_ticker(symbol)
        return _float_or_none(ticker.get("last") or ticker.get("close"))
    except Exception:
        return None


async def _get_position(executor: CCXTTradeExecutor, symbol: str) -> Optional[Dict[str, Any]]:
    positions = await executor._client.fetch_positions([symbol])
    for pos in positions:
        if _position_size(pos) > 0:
            return pos
    return None


async def test_read_operations(executor: CCXTTradeExecutor, symbol: str):
    """Test read-only operations (safe, no trades)."""
    print("\n" + "=" * 60)
    print("TESTING READ OPERATIONS (Safe)")
    print("=" * 60)

    # Test 1: Balance snapshot
    print("\n[1] Testing fetch_balance()...")
    try:
        balance = await executor._client.fetch_balance()
        quote = QUOTE_ASSET.upper()
        asset = balance.get(quote, {})
        total = _float_or_none(asset.get("total")) or 0.0
        free = _float_or_none(asset.get("free")) or 0.0
        used = _float_or_none(asset.get("used")) or 0.0
        print(f"    ✓ {quote} Total: {total:.4f}")
        print(f"    ✓ {quote} Free:  {free:.4f}")
        print(f"    ✓ {quote} Used:  {used:.4f}")
    except Exception as e:
        print(f"    ✗ FAILED: {e}")

    # Test 2: Get open positions
    print("\n[2] Testing fetch_positions()...")
    try:
        positions = await executor._client.fetch_positions([symbol])
        active = [p for p in positions if _position_size(p) > 0]
        print(f"    ✓ Found {len(active)} open position(s)")
        for pos in active:
            side = _position_side(pos)
            size = _position_size(pos)
            entry = _position_entry_price(pos) or 0.0
            mark = _float_or_none(pos.get("markPrice")) or 0.0
            pnl = _float_or_none(pos.get("unrealizedPnl")) or 0.0
            print(f"      - {pos.get('symbol', symbol)} {side}: size={size:.4f}, entry=${entry:.2f}, mark=${mark:.2f}, pnl=${pnl:.2f}")
    except Exception as e:
        print(f"    ✗ FAILED: {e}")

    # Test 3: Get open orders
    print("\n[3] Testing fetch_open_orders()...")
    try:
        orders = await executor._client.fetch_open_orders(symbol)
        print(f"    ✓ Found {len(orders)} order(s)")
        for order in orders[:5]:
            print(f"      - {order.get('symbol')} {order.get('side')} @ {order.get('price')} (type: {order.get('type')})")
    except Exception as e:
        print(f"    ✗ FAILED: {e}")

    # Test 4: Get current price
    print(f"\n[4] Testing fetch_ticker('{symbol}')...")
    try:
        price = await _fetch_ticker(executor, symbol)
        print(f"    ✓ {symbol} price: ${price:.2f}" if price else "    ✗ No price data")
    except Exception as e:
        print(f"    ✗ FAILED: {e}")


async def test_open_position(executor: CCXTTradeExecutor, symbol: str):
    """Test opening a small market position."""
    print("\n" + "=" * 60)
    print(f"TESTING OPEN POSITION ({TEST_SYMBOL} LONG ${TEST_SIZE_USD})")
    print("=" * 60)

    confirm = input("\nThis will open a REAL position. Continue? (yes/no): ")
    if confirm.lower() != "yes":
        print("Skipped.")
        return None

    try:
        decision = ExecutionIdea(
            action=ExecutionAction.OPEN_LONG,
            symbol=TEST_SYMBOL,
            position_size_usd=TEST_SIZE_USD,
            leverage=TEST_LEVERAGE,
        )
        result = await executor.execute(decision)
        print("\nResult:")
        print(f"  Success: {result.success}")
        print(f"  Order ID: {result.order_id}")
        print(f"  Fill Price: {result.fill_price}")
        print(f"  Filled Size: {result.filled_size}")
        print(f"  Status: {result.status}")
        if result.error:
            print(f"  Error: {result.error}")
        return result
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        return None


async def test_open_limit_position(executor: CCXTTradeExecutor, symbol: str):
    """Test opening a limit order position."""
    print("\n" + "=" * 60)
    print(f"TESTING OPEN LIMIT POSITION ({TEST_SYMBOL})")
    print("=" * 60)

    current_price = await _fetch_ticker(executor, symbol)
    if not current_price:
        print(f"Could not get current price for {symbol}")
        return None

    print(f"\nCurrent {symbol} price: ${current_price:.2f}")
    print("\nLimit Order Options:")
    print(f"  1. LONG limit (buy below market) - e.g., ${current_price * 0.99:.2f}")
    print(f"  2. SHORT limit (sell above market) - e.g., ${current_price * 1.01:.2f}")
    print("  0. Cancel")

    choice = input("\nEnter choice: ").strip()
    if choice == "0":
        print("Cancelled.")
        return None
    if choice == "1":
        action = ExecutionAction.OPEN_LONG_LIMIT
        suggested_price = current_price * 0.99
    elif choice == "2":
        action = ExecutionAction.OPEN_SHORT_LIMIT
        suggested_price = current_price * 1.01
    else:
        print("Invalid choice.")
        return None

    price_input = input(f"\nEnter limit price (default: ${suggested_price:.2f}): ").strip()
    if price_input:
        try:
            limit_price = float(price_input)
        except ValueError:
            print("Invalid price.")
            return None
    else:
        limit_price = suggested_price

    print("\nTime in Force options:")
    print("  1. Gtc (Good til Cancel)")
    print("  2. Ioc (Immediate or Cancel)")
    print("  3. Alo (Post-only)")

    tif_choice = input("\nEnter TIF choice (default: 1): ").strip() or "1"
    tif_map = {"1": "Gtc", "2": "Ioc", "3": "Alo"}
    time_in_force = tif_map.get(tif_choice, "Gtc")

    print("\n--- Order Summary ---")
    print(f"  Action: {action.value}")
    print(f"  Symbol: {TEST_SYMBOL}")
    print(f"  Size: ${TEST_SIZE_USD}")
    print(f"  Limit Price: ${limit_price:.2f}")
    print(f"  Time in Force: {time_in_force}")
    print(f"  Leverage: {TEST_LEVERAGE}x")

    confirm = input("\nPlace this LIMIT order? (yes/no): ")
    if confirm.lower() != "yes":
        print("Skipped.")
        return None

    try:
        decision = ExecutionIdea(
            action=action,
            symbol=TEST_SYMBOL,
            position_size_usd=TEST_SIZE_USD,
            limit_price=limit_price,
            time_in_force=time_in_force,
            leverage=TEST_LEVERAGE,
        )
        result = await executor.execute(decision)
        print("\nResult:")
        print(f"  Success: {result.success}")
        print(f"  Order ID: {result.order_id}")
        print(f"  Fill Price: {result.fill_price}")
        print(f"  Filled Size: {result.filled_size}")
        print(f"  Status: {result.status}")
        if result.error:
            print(f"  Error: {result.error}")
        return result
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        return None


async def test_set_stop_loss(executor: CCXTTradeExecutor, symbol: str):
    """Test setting a stop loss (via set_sl_tp)."""
    print("\n" + "=" * 60)
    print(f"TESTING SET STOP LOSS ({TEST_SYMBOL})")
    print("=" * 60)

    position = await _get_position(executor, symbol)
    if not position:
        print(f"No open position for {TEST_SYMBOL}. Skipping SL test.")
        return None

    entry = _position_entry_price(position) or (await _fetch_ticker(executor, symbol)) or 0.0
    if entry <= 0:
        print("Could not determine a valid entry/market price. Skipping.")
        return None
    side = _position_side(position)
    if side == "long":
        sl_price = entry * 0.95
    else:
        sl_price = entry * 1.05

    print(f"Position: {side.upper()} @ ${entry:.2f}")
    print(f"Proposed SL: ${sl_price:.2f}")
    confirm = input("\nSet this stop loss? (yes/no): ")
    if confirm.lower() != "yes":
        print("Skipped.")
        return None

    try:
        result = await executor.set_sl_tp(symbol, stop_loss_price=sl_price)
        _print_last_ccxt_request(executor, "set_stop_loss")
        print("\nResult:")
        print(f"  Success: {result.success}")
        print(f"  Order ID: {result.order_id}")
        print(f"  Status: {result.status}")
        if result.error:
            print(f"  Error: {result.error}")
        return result
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        return None


async def test_set_take_profit(executor: CCXTTradeExecutor, symbol: str):
    """Test setting a take profit (via set_sl_tp)."""
    print("\n" + "=" * 60)
    print(f"TESTING SET TAKE PROFIT ({TEST_SYMBOL})")
    print("=" * 60)

    position = await _get_position(executor, symbol)
    if not position:
        print(f"No open position for {TEST_SYMBOL}. Skipping TP test.")
        return None

    entry = _position_entry_price(position) or (await _fetch_ticker(executor, symbol)) or 0.0
    if entry <= 0:
        print("Could not determine a valid entry/market price. Skipping.")
        return None
    side = _position_side(position)
    if side == "long":
        tp_price = entry * 1.05
    else:
        tp_price = entry * 0.95

    print(f"Position: {side.upper()} @ ${entry:.2f}")
    print(f"Proposed TP: ${tp_price:.2f}")
    confirm = input("\nSet this take profit? (yes/no): ")
    if confirm.lower() != "yes":
        print("Skipped.")
        return None

    try:
        result = await executor.set_sl_tp(symbol, take_profit_price=tp_price)
        _print_last_ccxt_request(executor, "set_take_profit")
        print("\nResult:")
        print(f"  Success: {result.success}")
        print(f"  Order ID: {result.order_id}")
        print(f"  Status: {result.status}")
        if result.error:
            print(f"  Error: {result.error}")
        return result
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        return None


async def test_update_stop_loss(executor: CCXTTradeExecutor, symbol: str):
    """Test updating (moving) a stop loss."""
    print("\n" + "=" * 60)
    print(f"TESTING UPDATE STOP LOSS ({TEST_SYMBOL})")
    print("=" * 60)

    position = await _get_position(executor, symbol)
    if not position:
        print(f"No open position for {TEST_SYMBOL}. Skipping.")
        return None

    entry = _position_entry_price(position) or (await _fetch_ticker(executor, symbol)) or 0.0
    if entry <= 0:
        print("Could not determine a valid entry/market price. Skipping.")
        return None
    side = _position_side(position)
    if side == "long":
        new_sl_price = entry * 0.97
    else:
        new_sl_price = entry * 1.03

    print(f"Position: {side.upper()} @ ${entry:.2f}")
    print(f"New SL: ${new_sl_price:.2f}")
    confirm = input("\nUpdate stop loss? (yes/no): ")
    if confirm.lower() != "yes":
        print("Skipped.")
        return None

    try:
        decision = ExecutionIdea(
            action=ExecutionAction.UPDATE_SL,
            symbol=TEST_SYMBOL,
            new_stop_loss=new_sl_price,
        )
        result = await executor.execute(decision)
        _print_last_ccxt_request(executor, "update_stop_loss")
        print("\nResult:")
        print(f"  Success: {result.success}")
        print(f"  Order ID: {result.order_id}")
        print(f"  Status: {result.status}")
        if result.error:
            print(f"  Error: {result.error}")
        return result
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        return None


async def test_update_take_profit(executor: CCXTTradeExecutor, symbol: str):
    """Test updating (moving) a take profit."""
    print("\n" + "=" * 60)
    print(f"TESTING UPDATE TAKE PROFIT ({TEST_SYMBOL})")
    print("=" * 60)

    position = await _get_position(executor, symbol)
    if not position:
        print(f"No open position for {TEST_SYMBOL}. Skipping.")
        return None

    entry = _position_entry_price(position) or (await _fetch_ticker(executor, symbol)) or 0.0
    if entry <= 0:
        print("Could not determine a valid entry/market price. Skipping.")
        return None
    side = _position_side(position)
    if side == "long":
        new_tp_price = entry * 1.03
    else:
        new_tp_price = entry * 0.97

    print(f"Position: {side.upper()} @ ${entry:.2f}")
    print(f"New TP: ${new_tp_price:.2f}")
    confirm = input("\nUpdate take profit? (yes/no): ")
    if confirm.lower() != "yes":
        print("Skipped.")
        return None

    try:
        decision = ExecutionIdea(
            action=ExecutionAction.UPDATE_TP,
            symbol=TEST_SYMBOL,
            new_take_profit=new_tp_price,
        )
        result = await executor.execute(decision)
        _print_last_ccxt_request(executor, "update_take_profit")
        print("\nResult:")
        print(f"  Success: {result.success}")
        print(f"  Order ID: {result.order_id}")
        print(f"  Status: {result.status}")
        if result.error:
            print(f"  Error: {result.error}")
        return result
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        return None


async def test_cancel_trigger_orders(executor: CCXTTradeExecutor, symbol: str):
    """Test cancelling trigger orders (SL/TP) via executor actions."""
    print("\n" + "=" * 60)
    print(f"TESTING CANCEL TRIGGER ORDERS ({TEST_SYMBOL})")
    print("=" * 60)

    print("\nOptions:")
    print("  1. Cancel ALL trigger orders (SL + TP)")
    print("  2. Cancel only SL orders")
    print("  3. Cancel only TP orders")
    print("  0. Skip")

    choice = input("\nEnter choice: ").strip()
    if choice == "0":
        print("Skipped.")
        return None

    if choice == "1":
        action = ExecutionAction.CANCEL_SL_TP
    elif choice == "2":
        action = ExecutionAction.CANCEL_SL
    elif choice == "3":
        action = ExecutionAction.CANCEL_TP
    else:
        print("Invalid choice.")
        return None

    try:
        decision = ExecutionIdea(action=action, symbol=TEST_SYMBOL)
        result = await executor.execute(decision)
        print("\nResult:")
        print(f"  Success: {result.success}")
        print(f"  Status: {result.status}")
        if result.error:
            print(f"  Error: {result.error}")
        return result
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        return None


async def test_cancel_open_orders(executor: CCXTTradeExecutor, symbol: str):
    """Test cancelling open (resting) orders."""
    print("\n" + "=" * 60)
    print(f"TESTING CANCEL OPEN ORDERS ({TEST_SYMBOL})")
    print("=" * 60)

    try:
        open_orders = await executor._client.fetch_open_orders(symbol)
        if not open_orders:
            print(f"No open orders for {TEST_SYMBOL}.")
            return None

        print(f"\nFound {len(open_orders)} order(s) for {TEST_SYMBOL}:")
        for i, order in enumerate(open_orders):
            oid = order.get("id")
            side = order.get("side")
            price = order.get("price")
            amount = order.get("amount")
            order_type = order.get("type")
            print(f"  [{i+1}] id={oid} | {side} {amount} @ {price} | {order_type}")

        print("\nOptions:")
        print("  a. Cancel ALL orders for this symbol")
        print("  Enter number to cancel specific order")
        print("  0. Skip")

        choice = input("\nEnter choice: ").strip()
        if choice == "0":
            print("Skipped.")
            return None
        if choice.lower() == "a":
            confirm = input(f"\nCancel ALL {len(open_orders)} orders? (yes/no): ")
            if confirm.lower() != "yes":
                print("Skipped.")
                return None
            cancelled = 0
            for order in open_orders:
                oid = order.get("id")
                try:
                    await executor._client.cancel_order(oid, symbol)
                    cancelled += 1
                    print(f"  ✓ Cancelled order {oid}")
                except Exception as e:
                    print(f"  ✗ Failed to cancel {oid}: {e}")
            print(f"\nCancelled {cancelled}/{len(open_orders)} orders.")
            return {"cancelled": cancelled}

        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(open_orders):
                print("Invalid selection.")
                return None
            order = open_orders[idx]
            oid = order.get("id")
            confirm = input(f"\nCancel order {oid}? (yes/no): ")
            if confirm.lower() != "yes":
                print("Skipped.")
                return None
            await executor._client.cancel_order(oid, symbol)
            print("  ✓ Cancelled.")
            return {"cancelled": 1, "order_id": oid}
        except ValueError:
            print("Invalid input.")
            return None

    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        return None


async def test_list_trigger_orders(executor: CCXTTradeExecutor, symbol: str):
    """Display current trigger (SL/TP) orders for the symbol."""
    print("\n" + "=" * 60)
    print(f"TESTING LIST TRIGGER ORDERS ({TEST_SYMBOL})")
    print("=" * 60)

    try:
        orders = None
        market_id = None
        try:
            market = executor._client.market(symbol)
            if isinstance(market, dict):
                market_id = market.get("id")
        except Exception:
            market_id = None
        print(f"Resolved symbol: {symbol} | market id: {market_id or 'unknown'}")

        if EXCHANGE_ID.lower() == "binance":
            try:
                if not market_id:
                    print("  ✗ Binance all orders requires a market id (e.g., SOLUSDT).")
                else:
                    raw = await executor._client.fapiPrivateGetAllOrders({"symbol": market_id})
                    if isinstance(raw, list):
                        orders = raw
                        print(f"Using fapiPrivateGetAllOrders: {len(orders)} order(s)")
            except Exception as e:
                print(f"  ✗ Binance all orders fetch failed: {e}")

        if orders is None:
            orders = await executor._client.fetch_open_orders(symbol)

        if not orders:
            print("No open orders found.")
            return None

        position_side = None
        mark_price = None
        try:
            positions = await executor._client.fetch_positions([symbol])
            position = next((p for p in positions if p.get("contracts") or p.get("size")), None)
            if position:
                side = str(position.get("side") or "").lower()
                if not side and isinstance(position.get("info"), dict):
                    info = position["info"]
                    side = str(info.get("positionSide") or info.get("side") or info.get("posSide") or "").lower()
                if side in ("long", "short"):
                    position_side = side
                mark_price = _float_or_none(position.get("markPrice"))
        except Exception:
            position_side = None
            mark_price = None

        if mark_price is None:
            try:
                ticker = await executor._client.fetch_ticker(symbol)
                mark_price = _float_or_none(ticker.get("last") or ticker.get("close"))
            except Exception:
                mark_price = None

        def _dump_order(order: Dict[str, Any]) -> None:
            info = order.get("info") if isinstance(order.get("info"), dict) else {}
            status = order.get("status") or info.get("status")
            order_type = order.get("type") or info.get("type") or info.get("orderType")
            stop_price = order.get("stopPrice") or info.get("stopPrice") or info.get("triggerPrice") or info.get("triggerPx")
            reduce_only = order.get("reduceOnly") or info.get("reduceOnly")
            close_position = order.get("closePosition") or info.get("closePosition")
            order_id = order.get("id") or order.get("orderId") or info.get("orderId")
            side = order.get("side") or info.get("side") or order.get("positionSide") or info.get("positionSide")
            print(
                f"  - id={order_id} status={status} type={order_type} side={side} "
                f"stop={stop_price} reduceOnly={reduce_only} closePosition={close_position}"
            )

        print("\nAll orders (raw summary):")
        for order in orders:
            _dump_order(order)

        trigger_orders = []
        for order in orders:
            status = str(order.get("status") or "").upper()
            if status and status != "NEW":
                continue
            order_type = _extract_order_type(order)
            stop_price = _extract_stop_price(order)
            reduce_only = _extract_reduce_only(order)
            if order_type not in {"stop", "stop_market", "take_profit", "take_profit_market"} and not stop_price:
                continue
            if not _is_trigger_order(order_type, stop_price, reduce_only):
                continue

            kind = "unknown"
            if "take_profit" in order_type or "profit" in order_type:
                kind = "tp"
            elif "stop" in order_type:
                kind = "sl"
            elif stop_price is not None and mark_price is not None and position_side in ("long", "short"):
                if position_side == "long":
                    kind = "sl" if stop_price < mark_price else "tp"
                else:
                    kind = "sl" if stop_price > mark_price else "tp"

            order_id = order.get("id") or order.get("orderId")
            side = order.get("side") or order.get("positionSide") or ""
            trigger_orders.append(
                {
                    "id": order_id,
                    "type": order_type,
                    "kind": kind,
                    "side": side,
                    "stop": stop_price,
                    "price": order.get("price") or order.get("avgPrice") or order.get("limitPrice"),
                    "reduceOnly": reduce_only,
                }
            )

        if not trigger_orders:
            print("No trigger (SL/TP) orders found.")
            return None

        print(f"Found {len(trigger_orders)} trigger order(s):")
        for order in trigger_orders:
            print(
                f"  - id={order['id']} type={order['type']} kind={order['kind']} "
                f"side={order['side']} stop={order['stop']} reduceOnly={order['reduceOnly']}"
            )
        return trigger_orders

    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        return None


async def test_list_algo_orders(executor: CCXTTradeExecutor, symbol: str):
    """List Binance futures algo (conditional) orders for the symbol."""
    print("\n" + "=" * 60)
    print(f"TESTING LIST ALGO ORDERS ({TEST_SYMBOL})")
    print("=" * 60)

    if EXCHANGE_ID.lower() != "binance":
        print("Not a Binance exchange config. Skipping.")
        return None

    market_id = None
    try:
        market = executor._client.market(symbol)
        if isinstance(market, dict):
            market_id = market.get("id")
    except Exception:
        market_id = None

    if not market_id:
        print("Could not resolve market id (e.g., SOLUSDT).")
        return None

    params: Dict[str, Any] = {"symbol": market_id, "algoType": "CONDITIONAL"}
    results = []

    for method_name in ("fapiPrivateGetOpenAlgoOrders", "fapiPrivateGetAllAlgoOrders"):
        if hasattr(executor._client, method_name):
            try:
                method = getattr(executor._client, method_name)
                response = await method(params)
                print(f"{method_name} returned type={type(response).__name__}")
                results.append((method_name, response))
            except Exception as exc:
                print(f"{method_name} failed: {exc}")

    for path in ("openAlgoOrders", "allAlgoOrders"):
        try:
            response = await executor._client.request(path, "fapiPrivate", "GET", params)
            print(f"request GET {path} returned type={type(response).__name__}")
            results.append((path, response))
        except Exception as exc:
            print(f"request GET {path} failed: {exc}")

    if not results:
        print("No algo-order responses returned.")
        return None

    for label, response in results:
        print(f"\n--- {label} response ---")
        if isinstance(response, list):
            print(f"Count: {len(response)}")
            for order in response[:20]:
                print(order)
            if len(response) > 20:
                print(f"... and {len(response) - 20} more")
        else:
            print(response)

    return results


async def test_binance_diagnostics(executor: CCXTTradeExecutor, symbol: str):
    """Dump basic Binance USDT-M futures diagnostics (read-only)."""
    print("\n" + "=" * 60)
    print("BINANCE FUTURES DIAGNOSTICS (READ-ONLY)")
    print("=" * 60)

    if EXCHANGE_ID.lower() != "binance":
        print("Not a Binance exchange config. Skipping.")
        return None

    market_id = None
    try:
        market = executor._client.market(symbol)
        if isinstance(market, dict):
            market_id = market.get("id")
    except Exception:
        market_id = None

    print(f"Resolved symbol: {symbol} | market id: {market_id or 'unknown'}")

    # Account summary
    try:
        account = await executor._client.fapiPrivateGetAccount()
        total_margin_balance = _float_or_none(account.get("totalMarginBalance"))
        total_wallet_balance = _float_or_none(account.get("totalWalletBalance"))
        available_balance = _float_or_none(account.get("availableBalance"))
        print("\nAccount:")
        print(f"  totalMarginBalance: {total_margin_balance}")
        print(f"  totalWalletBalance: {total_wallet_balance}")
        print(f"  availableBalance:   {available_balance}")
    except Exception as e:
        print(f"\nAccount fetch failed: {e}")

    # Positions
    try:
        positions = await executor._client.fapiPrivateGetPositionRisk()
        active = [
            p for p in positions
            if _float_or_none(p.get("positionAmt")) not in (None, 0.0)
        ]
        print(f"\nOpen positions: {len(active)}")
        for pos in active[:10]:
            print(
                f"  - {pos.get('symbol')} amt={pos.get('positionAmt')} "
                f"entry={pos.get('entryPrice')} unrealized={pos.get('unRealizedProfit')}"
            )
        if len(active) > 10:
            print(f"  ... and {len(active) - 10} more")
    except Exception as e:
        print(f"\nPositions fetch failed: {e}")

    # Open orders (all)
    try:
        orders = await executor._client.fapiPrivateGetOpenOrders({})
        if isinstance(orders, list):
            print(f"\nOpen orders (all symbols): {len(orders)}")
            if orders:
                symbols = sorted({str(o.get('symbol') or '') for o in orders if o.get('symbol')})
                if symbols:
                    print(f"  symbols: {', '.join(symbols[:10])}")
                    if len(symbols) > 10:
                        print(f"  ... and {len(symbols) - 10} more")
        else:
            print("\nOpen orders (all symbols): unexpected response")
    except Exception as e:
        print(f"\nOpen orders fetch failed: {e}")

    # Open orders (symbol)
    if market_id:
        try:
            orders = await executor._client.fapiPrivateGetOpenOrders({"symbol": market_id})
            if isinstance(orders, list):
                print(f"\nOpen orders ({market_id}): {len(orders)}")
            else:
                print(f"\nOpen orders ({market_id}): unexpected response")
        except Exception as e:
            print(f"\nOpen orders ({market_id}) fetch failed: {e}")

    return True


async def test_close_position(executor: CCXTTradeExecutor, symbol: str):
    """Test closing a position."""
    print("\n" + "=" * 60)
    print(f"TESTING CLOSE POSITION ({TEST_SYMBOL})")
    print("=" * 60)

    position = await _get_position(executor, symbol)
    if not position:
        print(f"No open position for {TEST_SYMBOL}. Skipping.")
        return None

    side = _position_side(position)
    size = _position_size(position)
    entry = _position_entry_price(position) or 0.0
    print(f"Position: {side.upper()} {size:.4f} @ ${entry:.2f}")

    confirm = input("\nClose this position? (yes/no): ")
    if confirm.lower() != "yes":
        print("Skipped.")
        return None

    try:
        decision = ExecutionIdea(action=ExecutionAction.CLOSE, symbol=TEST_SYMBOL)
        result = await executor.execute(decision)
        print("\nResult:")
        print(f"  Success: {result.success}")
        print(f"  Order ID: {result.order_id}")
        print(f"  Fill Price: {result.fill_price}")
        print(f"  Filled Size: {result.filled_size}")
        print(f"  Status: {result.status}")
        if result.error:
            print(f"  Error: {result.error}")
        return result
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        return None


async def test_reduce_position(executor: CCXTTradeExecutor, symbol: str):
    """Test reducing a position by percentage."""
    print("\n" + "=" * 60)
    print(f"TESTING REDUCE POSITION ({TEST_SYMBOL})")
    print("=" * 60)

    position = await _get_position(executor, symbol)
    if not position:
        print(f"No open position for {TEST_SYMBOL}. Skipping.")
        return None

    side = _position_side(position)
    size = _position_size(position)
    entry = _position_entry_price(position) or 0.0
    print(f"Position: {side.upper()} {size:.4f} @ ${entry:.2f}")

    reduce_pct = input("\nEnter reduce percentage (e.g., 50): ").strip()
    try:
        reduce_pct = float(reduce_pct)
    except ValueError:
        print("Invalid percentage.")
        return None

    if reduce_pct <= 0 or reduce_pct > 100:
        print("Percentage must be between 0 and 100.")
        return None

    confirm = input(f"\nReduce position by {reduce_pct}%? (yes/no): ")
    if confirm.lower() != "yes":
        print("Skipped.")
        return None

    try:
        decision = ExecutionIdea(
            action=ExecutionAction.REDUCE,
            symbol=TEST_SYMBOL,
            reduce_pct=reduce_pct,
        )
        result = await executor.execute(decision)
        print("\nResult:")
        print(f"  Success: {result.success}")
        print(f"  Order ID: {result.order_id}")
        print(f"  Fill Price: {result.fill_price}")
        print(f"  Filled Size: {result.filled_size}")
        print(f"  Status: {result.status}")
        if result.error:
            print(f"  Error: {result.error}")
        return result
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        return None


async def main():
    print("=" * 60)
    print("CCXT EXECUTOR TEST SCRIPT")
    print("=" * 60)

    if not API_KEY or not API_SECRET:
        print("\n❌ ERROR: Please fill in API_KEY and API_SECRET at the top of this script.")
        return

    config = CCXTTradeConfig(
        exchange_id=EXCHANGE_ID,
        api_key=API_KEY,
        api_secret=API_SECRET,
        passphrase=PASSPHRASE or None,
        is_testnet=IS_TESTNET,
        quote_asset=QUOTE_ASSET,
    )

    print("\nInitializing executor...")
    print(f"  Exchange: {EXCHANGE_ID}")
    print(f"  Testnet: {IS_TESTNET}")
    print(f"  Symbol: {TEST_SYMBOL}")

    async with CCXTTradeExecutor(config) as executor:
        symbol = executor._normalize_symbol(TEST_SYMBOL)
        while True:
            print("\n" + "-" * 40)
            print("SELECT TEST:")
            print("  1. Read operations (safe)")
            print("  2. Open position (market)")
            print("  3. Open position (LIMIT)")
            print("  4. Set stop loss")
            print("  5. Set take profit")
            print("  6. Update stop loss")
            print("  7. Update take profit")
            print("  8. Cancel trigger orders (SL/TP)")
            print("  9. Cancel open orders (limit)")
            print("  10. Close position")
            print("  11. Reduce position")
            print("  12. List trigger orders (SL/TP)")
            print("  13. Binance futures diagnostics (read-only)")
            print("  14. List algo orders (Binance conditional)")
            print("  0. Exit")
            print("-" * 40)

            choice = input("Enter choice: ").strip()

            if choice == "0":
                print("Exiting.")
                break
            elif choice == "1":
                await test_read_operations(executor, symbol)
            elif choice == "2":
                await test_open_position(executor, symbol)
            elif choice == "3":
                await test_open_limit_position(executor, symbol)
            elif choice == "4":
                await test_set_stop_loss(executor, symbol)
            elif choice == "5":
                await test_set_take_profit(executor, symbol)
            elif choice == "6":
                await test_update_stop_loss(executor, symbol)
            elif choice == "7":
                await test_update_take_profit(executor, symbol)
            elif choice == "8":
                await test_cancel_trigger_orders(executor, symbol)
            elif choice == "9":
                await test_cancel_open_orders(executor, symbol)
            elif choice == "10":
                await test_close_position(executor, symbol)
            elif choice == "11":
                await test_reduce_position(executor, symbol)
            elif choice == "12":
                await test_list_trigger_orders(executor, symbol)
            elif choice == "13":
                await test_binance_diagnostics(executor, symbol)
            elif choice == "14":
                await test_list_algo_orders(executor, symbol)
            else:
                print("Invalid choice.")


if __name__ == "__main__":
    asyncio.run(main())
