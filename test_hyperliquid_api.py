#!/usr/bin/env python3
"""
Hyperliquid API Test Script

Tests the HyperliquidExecutor methods to verify API connectivity and functionality.
Run with: python test_hyperliquid_api.py

IMPORTANT: Fill in your credentials below before running!
"""

import asyncio
import sys

# Add project root to path
sys.path.insert(0, '.')

from app.infrastructure.external.hyperliquid_executor import HyperliquidExecutor

# =============================================================================
# CONFIGURATION - Fill these in!
# =============================================================================

AGENT_PRIVATE_KEY = "0x5190168791ac02e3f4e74d28965d693d2d47df8cc00c5550f9eecbb24ff366e1"  # Your agent wallet private key (for signing)
MAIN_WALLET_ADDRESS = "0x0Cb71b066f11F1B753a35B11a6aa86f89878609e"  # Your main wallet address (for querying)

# Test settings
TEST_SYMBOL = "BTC"  # Symbol to test with
TEST_SIZE_USD = 20  # Small size for testing ($20)
TEST_LEVERAGE = 1

# =============================================================================
# TEST FUNCTIONS
# =============================================================================

async def test_read_operations(executor: HyperliquidExecutor):
    """Test read-only operations (safe, no trades)."""
    print("\n" + "="*60)
    print("TESTING READ OPERATIONS (Safe)")
    print("="*60)
    
    # Test 1: Get account state
    print("\n[1] Testing get_account_state()...")
    try:
        state = await executor.get_account_state()
        print(f"    ✓ Account Value: ${state.account_value:.2f}")
        print(f"    ✓ Available Margin: ${state.available_margin:.2f}")
        print(f"    ✓ Unrealized PnL: ${state.unrealized_pnl:.2f}")
        print(f"    ✓ Open Positions: {state.open_positions_count}")
    except Exception as e:
        print(f"    ✗ FAILED: {e}")
    
    # Test 2: Get open positions
    print("\n[2] Testing get_open_positions()...")
    try:
        positions = await executor.get_open_positions()
        print(f"    ✓ Found {len(positions)} position(s)")
        for pos in positions:
            print(f"      - {pos.symbol} {pos.direction}: size={pos.size:.4f}, entry=${pos.entry_price:.2f}, pnl=${pos.unrealized_pnl:.2f}")
    except Exception as e:
        print(f"    ✗ FAILED: {e}")
    
    # Test 3: Get open orders
    print("\n[3] Testing get_open_orders()...")
    try:
        orders = await executor.get_open_orders()
        print(f"    ✓ Found {len(orders)} order(s)")
        for order in orders[:5]:  # Show first 5
            print(f"      - {order.get('coin')} {order.get('side')} @ {order.get('limitPx')} (type: {order.get('orderType')})")
    except Exception as e:
        print(f"    ✗ FAILED: {e}")
    
    # Test 4: Get current price
    print(f"\n[4] Testing _get_current_price('{TEST_SYMBOL}')...")
    try:
        price = executor._get_current_price(TEST_SYMBOL)
        print(f"    ✓ {TEST_SYMBOL} price: ${price:.2f}")
    except Exception as e:
        print(f"    ✗ FAILED: {e}")
    
    return True


async def test_open_position(executor: HyperliquidExecutor):
    """Test opening a small position."""
    print("\n" + "="*60)
    print(f"TESTING OPEN POSITION ({TEST_SYMBOL} LONG ${TEST_SIZE_USD})")
    print("="*60)
    
    confirm = input("\nThis will open a REAL position. Continue? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Skipped.")
        return None
    
    try:
        result = await executor.open_position(
            symbol=TEST_SYMBOL,
            direction="LONG",
            size_usd=TEST_SIZE_USD,
            leverage=TEST_LEVERAGE
        )
        print(f"\nResult:")
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


async def test_set_stop_loss(executor: HyperliquidExecutor, symbol: str = TEST_SYMBOL):
    """Test setting a stop loss."""
    print("\n" + "="*60)
    print(f"TESTING SET STOP LOSS ({symbol})")
    print("="*60)
    
    # Get current position to calculate SL price
    positions = await executor.get_open_positions()
    position = next((p for p in positions if p.symbol.upper() == symbol.upper()), None)
    
    if not position:
        print(f"No open position for {symbol}. Skipping SL test.")
        return None
    
    # Set SL 5% below entry for LONG, 5% above for SHORT
    if position.direction == "LONG":
        sl_price = position.entry_price * 0.95
    else:
        sl_price = position.entry_price * 1.05
    
    print(f"Position: {position.direction} @ ${position.entry_price:.2f}")
    print(f"Proposed SL: ${sl_price:.2f}")
    
    confirm = input("\nSet this stop loss? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Skipped.")
        return None
    
    try:
        result = await executor.set_stop_loss(symbol, sl_price)
        print(f"\nResult:")
        print(f"  Success: {result.success}")
        print(f"  Order ID: {result.order_id}")
        print(f"  Status: {result.status}")
        if result.error:
            print(f"  Error: {result.error}")
        return result
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        return None


async def test_update_stop_loss(executor: HyperliquidExecutor, symbol: str = TEST_SYMBOL):
    """Test updating (moving) a stop loss."""
    print("\n" + "="*60)
    print(f"TESTING UPDATE STOP LOSS ({symbol})")
    print("="*60)
    
    positions = await executor.get_open_positions()
    position = next((p for p in positions if p.symbol.upper() == symbol.upper()), None)
    
    if not position:
        print(f"No open position for {symbol}. Skipping.")
        return None
    
    # Move SL closer (3% instead of 5%)
    if position.direction == "LONG":
        new_sl_price = position.entry_price * 0.97
    else:
        new_sl_price = position.entry_price * 1.03
    
    print(f"Position: {position.direction} @ ${position.entry_price:.2f}")
    print(f"New SL: ${new_sl_price:.2f}")
    
    confirm = input("\nUpdate stop loss? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Skipped.")
        return None
    
    try:
        result = await executor.update_stop_loss(symbol, new_sl_price)
        print(f"\nResult:")
        print(f"  Success: {result.success}")
        print(f"  Order ID: {result.order_id}")
        print(f"  Status: {result.status}")
        if result.error:
            print(f"  Error: {result.error}")
        return result
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        return None


async def test_update_take_profit(executor: HyperliquidExecutor, symbol: str = TEST_SYMBOL):
    """Test updating (moving) a take profit."""
    print("\n" + "="*60)
    print(f"TESTING UPDATE TAKE PROFIT ({symbol})")
    print("="*60)
    
    positions = await executor.get_open_positions()
    position = next((p for p in positions if p.symbol.upper() == symbol.upper()), None)
    
    if not position:
        print(f"No open position for {symbol}. Skipping.")
        return None
    
    # Move TP closer (3% instead of 5%)
    if position.direction == "LONG":
        new_tp_price = position.entry_price * 1.03
    else:
        new_tp_price = position.entry_price * 0.97
    
    print(f"Position: {position.direction} @ ${position.entry_price:.2f}")
    print(f"New TP: ${new_tp_price:.2f}")
    
    confirm = input("\nUpdate take profit? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Skipped.")
        return None
    
    try:
        result = await executor.update_take_profit(symbol, new_tp_price)
        print(f"\nResult:")
        print(f"  Success: {result.success}")
        print(f"  Order ID: {result.order_id}")
        print(f"  Status: {result.status}")
        if result.error:
            print(f"  Error: {result.error}")
        return result
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        return None


async def test_close_position(executor: HyperliquidExecutor, symbol: str = TEST_SYMBOL):
    """Test closing a position."""
    print("\n" + "="*60)
    print(f"TESTING CLOSE POSITION ({symbol})")
    print("="*60)
    
    positions = await executor.get_open_positions()
    position = next((p for p in positions if p.symbol.upper() == symbol.upper()), None)
    
    if not position:
        print(f"No open position for {symbol}. Skipping.")
        return None
    
    print(f"Position: {position.direction} {position.size} @ ${position.entry_price:.2f}")
    print(f"Current PnL: ${position.unrealized_pnl:.2f}")
    
    confirm = input("\nClose this position? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Skipped.")
        return None
    
    try:
        result = await executor.close_position(symbol)
        print(f"\nResult:")
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
        import traceback
        traceback.print_exc()
        return None


async def test_reduce_position(executor: HyperliquidExecutor, symbol: str = TEST_SYMBOL):
    """Test reducing a position by percentage."""
    print("\n" + "="*60)
    print(f"TESTING REDUCE POSITION ({symbol})")
    print("="*60)
    
    positions = await executor.get_open_positions()
    position = next((p for p in positions if p.symbol.upper() == symbol.upper()), None)
    
    if not position:
        print(f"No open position for {symbol}. Skipping.")
        return None
    
    print(f"Position: {position.direction} {position.size} @ ${position.entry_price:.2f}")
    print(f"Current PnL: ${position.unrealized_pnl:.2f}")
    
    reduce_pct = input("\nEnter reduce percentage (e.g., 50): ").strip()
    try:
        reduce_pct = float(reduce_pct)
    except:
        print("Invalid percentage.")
        return None
    
    if reduce_pct <= 0 or reduce_pct > 100:
        print("Percentage must be between 0 and 100.")
        return None
    
    confirm = input(f"\nReduce position by {reduce_pct}%? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Skipped.")
        return None
    
    try:
        result = await executor.reduce_position(symbol, reduce_pct)
        print(f"\nResult:")
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
        import traceback
        traceback.print_exc()
        return None


async def test_open_limit_position(executor: HyperliquidExecutor):
    """Test opening a limit order position."""
    print("\n" + "="*60)
    print(f"TESTING OPEN LIMIT POSITION ({TEST_SYMBOL})")
    print("="*60)
    
    # Get current price for reference
    current_price = executor._get_current_price(TEST_SYMBOL)
    if not current_price:
        print(f"Could not get current price for {TEST_SYMBOL}")
        return None
    
    print(f"\nCurrent {TEST_SYMBOL} price: ${current_price:.2f}")
    print(f"\nLimit Order Options:")
    print(f"  1. LONG limit (buy below market) - e.g., ${current_price * 0.99:.2f}")
    print(f"  2. SHORT limit (sell above market) - e.g., ${current_price * 1.01:.2f}")
    print(f"  0. Cancel")
    
    choice = input("\nEnter choice: ").strip()
    
    if choice == '0':
        print("Cancelled.")
        return None
    elif choice == '1':
        direction = "LONG"
        suggested_price = current_price * 0.99  # 1% below market
    elif choice == '2':
        direction = "SHORT"
        suggested_price = current_price * 1.01  # 1% above market
    else:
        print("Invalid choice.")
        return None
    
    # Get limit price from user
    price_input = input(f"\nEnter limit price (default: ${suggested_price:.2f}): ").strip()
    if price_input:
        try:
            limit_price = float(price_input)
        except:
            print("Invalid price.")
            return None
    else:
        limit_price = suggested_price
    
    # Get time in force
    print("\nTime in Force options:")
    print("  1. Gtc (Good til Cancel) - stays on book until filled or cancelled")
    print("  2. Ioc (Immediate or Cancel) - fills immediately or cancels")
    print("  3. Alo (Add Liquidity Only) - only adds to book, never takes")
    
    tif_choice = input("\nEnter TIF choice (default: 1): ").strip() or "1"
    tif_map = {"1": "Gtc", "2": "Ioc", "3": "Alo"}
    time_in_force = tif_map.get(tif_choice, "Gtc")
    
    print(f"\n--- Order Summary ---")
    print(f"  Direction: {direction}")
    print(f"  Symbol: {TEST_SYMBOL}")
    print(f"  Size: ${TEST_SIZE_USD}")
    print(f"  Limit Price: ${limit_price:.2f}")
    print(f"  Time in Force: {time_in_force}")
    print(f"  Leverage: {TEST_LEVERAGE}x")
    
    confirm = input("\nPlace this LIMIT order? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Skipped.")
        return None
    
    try:
        result = await executor.open_position_limit(
            symbol=TEST_SYMBOL,
            direction=direction,
            size_usd=TEST_SIZE_USD,
            limit_price=limit_price,
            leverage=TEST_LEVERAGE,
            time_in_force=time_in_force
        )
        print(f"\nResult:")
        print(f"  Success: {result.success}")
        print(f"  Order ID: {result.order_id}")
        print(f"  Fill Price: {result.fill_price}")
        print(f"  Filled Size: {result.filled_size}")
        print(f"  Status: {result.status}")
        if result.error:
            print(f"  Error: {result.error}")
        
        if result.status == "resting":
            print(f"\n  ℹ️  Order is RESTING on the book at ${limit_price:.2f}")
            print(f"      It will fill when price reaches your limit.")
            print(f"      Use 'Cancel trigger orders' or check open orders to manage.")
        
        return result
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_cancel_open_orders(executor: HyperliquidExecutor, symbol: str = TEST_SYMBOL):
    """Test cancelling open (resting) orders."""
    print("\n" + "="*60)
    print(f"TESTING CANCEL OPEN ORDERS ({symbol})")
    print("="*60)
    
    # Get open orders
    print("\nFetching open orders...")
    try:
        all_orders = await executor.get_open_orders()
        symbol_orders = [o for o in all_orders if o.get("coin", "").upper() == symbol.upper()]
        
        if not symbol_orders:
            print(f"No open orders for {symbol}.")
            return None
        
        print(f"\nFound {len(symbol_orders)} order(s) for {symbol}:")
        for i, order in enumerate(symbol_orders):
            oid = order.get("oid")
            side = order.get("side")
            limit_px = order.get("limitPx")
            sz = order.get("sz")
            order_type = order.get("orderType")
            reduce_only = order.get("reduceOnly", False)
            
            order_desc = "LIMIT" if not reduce_only else "SL/TP"
            print(f"  [{i+1}] oid={oid} | {side} {sz} @ ${limit_px} | {order_desc}")
        
        print("\nOptions:")
        print("  a. Cancel ALL orders for this symbol")
        print("  Enter number to cancel specific order")
        print("  0. Skip")
        
        choice = input("\nEnter choice: ").strip()
        
        if choice == '0':
            print("Skipped.")
            return None
        elif choice.lower() == 'a':
            # Cancel all
            confirm = input(f"\nCancel ALL {len(symbol_orders)} orders? (yes/no): ")
            if confirm.lower() != 'yes':
                print("Skipped.")
                return None
            
            cancelled = 0
            for order in symbol_orders:
                oid = order.get("oid")
                try:
                    cancel_result = executor.exchange.cancel(symbol, oid)
                    if cancel_result and cancel_result.get("status") == "ok":
                        cancelled += 1
                        print(f"  ✓ Cancelled order {oid}")
                    else:
                        print(f"  ✗ Failed to cancel {oid}: {cancel_result}")
                except Exception as e:
                    print(f"  ✗ Error cancelling {oid}: {e}")
            
            print(f"\nCancelled {cancelled}/{len(symbol_orders)} orders.")
            return {"cancelled": cancelled}
        else:
            try:
                idx = int(choice) - 1
                if idx < 0 or idx >= len(symbol_orders):
                    print("Invalid selection.")
                    return None
                
                order = symbol_orders[idx]
                oid = order.get("oid")
                
                confirm = input(f"\nCancel order {oid}? (yes/no): ")
                if confirm.lower() != 'yes':
                    print("Skipped.")
                    return None
                
                cancel_result = executor.exchange.cancel(symbol, oid)
                print(f"\nResult: {cancel_result}")
                return cancel_result
            except ValueError:
                print("Invalid input.")
                return None
    
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_cancel_trigger_orders(executor: HyperliquidExecutor, symbol: str = TEST_SYMBOL):
    """Test cancelling trigger orders (SL/TP)."""
    print("\n" + "="*60)
    print(f"TESTING CANCEL TRIGGER ORDERS ({symbol})")
    print("="*60)
    
    # Get position info for context
    positions = await executor.get_open_positions()
    position = next((p for p in positions if p.symbol.upper() == symbol.upper()), None)
    
    if position:
        print(f"\nPosition: {position.direction} @ ${position.entry_price:.2f}")
    
    # Debug: Show all open orders first
    print("\n[DEBUG] Fetching all open orders...")
    try:
        all_orders = executor.info.open_orders(executor.user_address)
        symbol_orders = [o for o in all_orders if o.get("coin", "").upper() == symbol.upper()]
        print(f"[DEBUG] Orders for {symbol}: {len(symbol_orders)}")
        for order in symbol_orders:
            limit_px = float(order.get("limitPx", 0))
            reduce_only = order.get("reduceOnly", False)
            oid = order.get("oid")
            
            # Identify SL vs TP
            order_type = "unknown"
            if reduce_only and position:
                if position.direction == "LONG":
                    order_type = "SL" if limit_px < position.entry_price else "TP"
                else:
                    order_type = "SL" if limit_px > position.entry_price else "TP"
            
            print(f"[DEBUG]   - oid={oid} | price=${limit_px:.2f} | reduceOnly={reduce_only} | type={order_type}")
    except Exception as e:
        print(f"[DEBUG] Error fetching orders: {e}")
    
    print("\nOptions:")
    print("  1. Cancel ALL trigger orders")
    print("  2. Cancel only SL orders")
    print("  3. Cancel only TP orders")
    print("  0. Skip")
    
    choice = input("\nEnter choice: ").strip()
    
    if choice == '0':
        print("Skipped.")
        return None
    
    order_type = None
    if choice == '2':
        order_type = "sl"
    elif choice == '3':
        order_type = "tp"
    elif choice != '1':
        print("Invalid choice.")
        return None
    
    try:
        result = await executor.cancel_trigger_orders(symbol, order_type=order_type)
        print(f"\nResult:")
        print(f"  Success: {result.success}")
        print(f"  Cancelled: {result.order_id}")
        print(f"  Status: {result.status}")
        if result.error:
            print(f"  Error: {result.error}")
        return result
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_set_take_profit(executor: HyperliquidExecutor, symbol: str = TEST_SYMBOL):
    """Test setting a take profit."""
    print("\n" + "="*60)
    print(f"TESTING SET TAKE PROFIT ({symbol})")
    print("="*60)
    
    positions = await executor.get_open_positions()
    position = next((p for p in positions if p.symbol.upper() == symbol.upper()), None)
    
    if not position:
        print(f"No open position for {symbol}. Skipping TP test.")
        return None
    
    # Set TP 5% above entry for LONG, 5% below for SHORT
    if position.direction == "LONG":
        tp_price = position.entry_price * 1.05
    else:
        tp_price = position.entry_price * 0.95
    
    print(f"Position: {position.direction} @ ${position.entry_price:.2f}")
    print(f"Proposed TP: ${tp_price:.2f}")
    
    confirm = input("\nSet this take profit? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Skipped.")
        return None
    
    try:
        result = await executor.set_take_profit(symbol, tp_price)
        print(f"\nResult:")
        print(f"  Success: {result.success}")
        print(f"  Order ID: {result.order_id}")
        print(f"  Status: {result.status}")
        if result.error:
            print(f"  Error: {result.error}")
        return result
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        return None


async def main():
    print("="*60)
    print("HYPERLIQUID API TEST SCRIPT")
    print("="*60)
    
    # Validate configuration
    if not AGENT_PRIVATE_KEY or not MAIN_WALLET_ADDRESS:
        print("\n❌ ERROR: Please fill in AGENT_PRIVATE_KEY and MAIN_WALLET_ADDRESS at the top of this script!")
        return
    
    # Initialize executor
    print(f"\nInitializing executor...")
    print(f"  Main wallet: {MAIN_WALLET_ADDRESS[:10]}...{MAIN_WALLET_ADDRESS[-6:]}")
    
    executor = HyperliquidExecutor(
        private_key=AGENT_PRIVATE_KEY,
        user_address=MAIN_WALLET_ADDRESS,
        testnet=False  # Set to True for testnet
    )
    
    # Menu
    while True:
        print("\n" + "-"*40)
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
        print("  0. Exit")
        print("-"*40)
        
        choice = input("Enter choice: ").strip()
        
        if choice == '0':
            print("Exiting.")
            break
        elif choice == '1':
            await test_read_operations(executor)
        elif choice == '2':
            await test_open_position(executor)
        elif choice == '3':
            await test_open_limit_position(executor)
        elif choice == '4':
            await test_set_stop_loss(executor)
        elif choice == '5':
            await test_set_take_profit(executor)
        elif choice == '6':
            await test_update_stop_loss(executor)
        elif choice == '7':
            await test_update_take_profit(executor)
        elif choice == '8':
            await test_cancel_trigger_orders(executor)
        elif choice == '9':
            await test_cancel_open_orders(executor)
        elif choice == '10':
            await test_close_position(executor)
        elif choice == '11':
            await test_reduce_position(executor)
        else:
            print("Invalid choice.")


if __name__ == "__main__":
    asyncio.run(main())
