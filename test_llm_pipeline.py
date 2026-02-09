#!/usr/bin/env python3
"""
LLM Pipeline Test Script

Parse an LLM response -> trade guard -> circuit breaker -> executor.
Run with: python test_llm_pipeline.py --response-file /path/to/response.txt

WARNING: Use --execute to place real orders.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Prefer backend package over root-level app/
sys.path.insert(0, "backend/src")

from app.application.llm_response_worker.service import LlmResponseWorker
from app.application.trade_guard.dependencies import get_trade_guard_service
from app.application.circuit_breaker.dependencies import get_circuit_breaker_service
from app.application.trade_executor.dependencies import get_trade_executor_service
from app.application.portfolio.dependencies import get_portfolio_service
from app.domain.llm_response_worker.models import ExecutionIdea


LLM_RESPONSE = """
## Step 1: Natural Language Analysis
- Paste your LLM response here (or pass --response-file)

## Step 2. JSON Server Actions:
JSON_ARRAY
[{
  "action": "OPEN_LONG",
  "symbol": "我踏马来了",
  "tier": 3,
  "position_pct": 0.03,
  "new_stop_loss": 29.8,
  "stop_loss_roe": 0.12,
  "leverage": 2,
  "take_profit_roe": 0.25,
  "confidence": 62,
  "reasoning": "12h price is accepting/expanding above the upper Bollinger Band (no sharp snapback inside), consistent with band-walk behavior. 8h/12h EMA tunnel structure is bullish (price above tunnels), so direction does not conflict. Due to extreme extension, use probe sizing with invalidation below the breakout/upper-band area.",
  "execute": true
}]
"""


def _load_env_from_file(path: Path) -> None:
    if not path.exists():
        return
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception:
        return


def _read_text(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    try:
        return Path(path).read_text(encoding="utf-8")
    except Exception as exc:
        print(f"Failed to read file: {path} ({exc})")
        return None


def _load_response(args: argparse.Namespace) -> str:
    if args.response_file:
        content = _read_text(args.response_file)
        return content or ""
    if args.response:
        return args.response
    return LLM_RESPONSE


def _load_json_arg(value: Optional[str], file_path: Optional[str]) -> Optional[Any]:
    if file_path:
        text = _read_text(file_path)
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            print(f"Invalid JSON in {file_path}: {exc}")
            return None
    if value:
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            print(f"Invalid JSON argument: {exc}")
            return None
    return None


def _format_breaker(result) -> Dict[str, Any]:
    return {
        "allowed": result.allowed,
        "reasons": result.reasons,
        "checked_at": result.checked_at.isoformat(),
    }


def _summarize_final_order(
    decision: ExecutionIdea,
    price_hint: Optional[float],
    fill_price: Optional[float] = None,
) -> Dict[str, Any]:
    action = decision.action.value
    if action in ("OPEN_LONG", "OPEN_LONG_LIMIT"):
        side = "long"
    elif action in ("OPEN_SHORT", "OPEN_SHORT_LIMIT"):
        side = "short"
    else:
        side = action.lower()

    leverage = decision.leverage or 1
    if leverage <= 0:
        leverage = 1

    entry_price = (
        fill_price
        or decision.entry_price
        or decision.limit_price
        or price_hint
    )

    notional_value = decision.position_size_usd
    margin_used = None
    if notional_value is not None and leverage > 0:
        margin_used = notional_value / leverage

    sl_roe = None
    tp_roe = None
    if entry_price and entry_price > 0:
        if decision.stop_loss:
            if side == "long":
                sl_roe = (entry_price - decision.stop_loss) / entry_price * leverage
            elif side == "short":
                sl_roe = (decision.stop_loss - entry_price) / entry_price * leverage
        if decision.take_profit:
            if side == "long":
                tp_roe = (decision.take_profit - entry_price) / entry_price * leverage
            elif side == "short":
                tp_roe = (entry_price - decision.take_profit) / entry_price * leverage

    return {
        "ticker": decision.symbol,
        "entry_price": entry_price,
        "tp_price": decision.take_profit,
        "sl_price": decision.stop_loss,
        "tp_roe": tp_roe,
        "sl_roe": sl_roe,
        "side": side,
        "notional_value": notional_value,
        "leverage": leverage,
        "margin_used": margin_used,
    }


async def _fetch_portfolio() -> Tuple[Optional[dict], Optional[list]]:
    service = get_portfolio_service()
    try:
        snapshot = await service.get_portfolio_snapshot()
    except Exception as exc:
        print(f"Failed to fetch portfolio snapshot: {exc}")
        return None, None

    account_state = {
        "account_value": snapshot.state.account_value,
        "available_margin": snapshot.state.available_margin,
        "total_margin_used": snapshot.state.total_margin_used,
        "unrealized_pnl": snapshot.state.unrealized_pnl,
        "open_positions_count": snapshot.state.open_positions_count,
        "total_exposure_pct": snapshot.state.total_exposure_pct,
    }

    open_positions = []
    for position in snapshot.positions:
        open_positions.append(
            {
                "symbol": position.symbol,
                "direction": position.direction,
                "size": position.size,
                "entry_price": position.entry_price,
                "mark_price": position.mark_price,
                "unrealized_pnl": position.unrealized_pnl,
                "liquidation_price": position.liquidation_price,
                "margin": position.margin,
                "leverage": position.leverage,
                "position_value_usd": (
                    (position.size or 0) * (position.mark_price or 0)
                    if position.mark_price
                    else None
                ),
            }
        )

    return account_state, open_positions


async def _get_price_fetcher(symbol: str) -> Optional[Any]:
    if not symbol:
        return None
    service = get_portfolio_service()
    try:
        connector = await service.get_active_connector()
    except Exception:
        return None

    fetcher = getattr(connector, "fetch_ticker_price", None)
    if not callable(fetcher):
        return None

    try:
        price = await fetcher(symbol)
    except Exception:
        return None

    if price is None or price <= 0:
        return None

    symbol_upper = symbol.upper()

    def _fetch(sym: str) -> Optional[float]:
        if not sym:
            return None
        return price if sym.upper() == symbol_upper else None

    return _fetch


async def _get_market_data(decision: ExecutionIdea) -> Optional[dict]:
    if not decision or not decision.symbol:
        return None
    service = get_portfolio_service()
    try:
        connector = await service.get_active_connector()
    except Exception:
        return None

    market_data: Dict[str, Any] = {}

    limits_fetcher = getattr(connector, "fetch_market_limits", None)
    if callable(limits_fetcher):
        try:
            limits = await limits_fetcher(decision.symbol)
        except Exception:
            limits = None
        if isinstance(limits, dict):
            market_data.update(limits)

    price_fetcher = getattr(connector, "fetch_ticker_price", None)
    if callable(price_fetcher):
        try:
            price = await price_fetcher(decision.symbol)
        except Exception:
            price = None
        if price:
            market_data["reference_price"] = price

    if decision.action.value in ("OPEN_LONG_LIMIT", "OPEN_SHORT_LIMIT"):
        market_data.setdefault("order_type", "limit")
    else:
        market_data.setdefault("order_type", "market")

    if not market_data:
        return None
    market_data.setdefault("exchange_name", "exchange")
    return market_data


async def _fetch_open_orders(decision: ExecutionIdea) -> Optional[list]:
    if not decision or not decision.symbol:
        return None
    service = get_portfolio_service()
    try:
        return await service.get_open_orders([decision.symbol])
    except Exception:
        return None


async def run_pipeline(args: argparse.Namespace) -> int:
    _load_env_from_file(Path("backend/.env"))
    response = _load_response(args)
    if not response or not response.strip():
        print("No LLM response provided. Paste it into LLM_RESPONSE or pass --response-file.")
        return 1

    parser = LlmResponseWorker()
    parse_result = parser.parse(response)
    if not parse_result.success:
        print("Parse failed:")
        print(parse_result.error or "unknown error")
        return 1

    if not parse_result.ideas:
        print("No execution ideas parsed from response.")
        return 1

    idea_index = max(0, min(args.idea_index, len(parse_result.ideas) - 1))
    decision: ExecutionIdea = parse_result.ideas[idea_index]

    account_state = _load_json_arg(args.account_state_json, args.account_state_file)
    open_positions = _load_json_arg(args.open_positions_json, args.open_positions_file)

    if not args.skip_portfolio and (account_state is None or open_positions is None):
        fetched_state, fetched_positions = await _fetch_portfolio()
        account_state = account_state or fetched_state
        open_positions = open_positions or fetched_positions

    price_fetcher = await _get_price_fetcher(decision.symbol)
    market_data = await _get_market_data(decision)
    price_hint = price_fetcher(decision.symbol) if price_fetcher else None
    open_orders = None
    if decision.action.value in ("UPDATE_SL", "UPDATE_TP"):
        open_orders = await _fetch_open_orders(decision)

    guard_service = get_trade_guard_service()
    guard_result = await guard_service.validate(
        decision,
        account_state=account_state,
        market_data=market_data,
        open_orders=open_orders,
        open_positions=open_positions,
        price_fetcher=price_fetcher,
    )

    guard_payload = guard_result.to_dict()
    guarded_decision = guard_result.decision or decision

    breaker_service = get_circuit_breaker_service()
    breaker_result = breaker_service.evaluate(
        guarded_decision,
        account_state=account_state,
        open_positions=open_positions,
    )

    output = {
        "parse": {
            "ideas": [idea.to_dict() for idea in parse_result.ideas],
        },
        "selected_index": idea_index,
        "guard": guard_payload,
        "circuit_breaker": _format_breaker(breaker_result),
        "final_order": _summarize_final_order(guarded_decision, price_hint),
    }

    if not guard_result.is_valid:
        output["execution"] = {
            "attempted": False,
            "reason": "trade_guard_rejected",
        }
        print(json.dumps(output, indent=2, default=str))
        return 2

    if not breaker_result.allowed:
        output["execution"] = {
            "attempted": False,
            "reason": "circuit_breaker_blocked",
        }
        print(json.dumps(output, indent=2, default=str))
        return 3

    if not args.execute:
        output["execution"] = {
            "attempted": False,
            "reason": "execute_flag_not_set",
        }
        print(json.dumps(output, indent=2, default=str))
        return 0

    if not args.yes:
        confirm = input("This will place a real order. Continue? (yes/no): ")
        if confirm.strip().lower() != "yes":
            output["execution"] = {
                "attempted": False,
                "reason": "user_aborted",
            }
            print(json.dumps(output, indent=2, default=str))
            return 0

    executor = get_trade_executor_service()
    exec_result = await executor.execute(guarded_decision)
    output["final_order"] = _summarize_final_order(
        guarded_decision,
        price_hint,
        fill_price=getattr(exec_result, "fill_price", None),
    )
    output["execution"] = {
        "attempted": True,
        "result": exec_result.__dict__,
    }
    print(json.dumps(output, indent=2, default=str))
    return 0 if exec_result.success else 4


def main() -> int:
    parser = argparse.ArgumentParser(description="Test automation pipeline from LLM response to trade execution.")
    parser.add_argument("--response", help="Raw LLM response text")
    parser.add_argument("--response-file", help="Path to a file containing LLM response")
    parser.add_argument("--idea-index", type=int, default=0, help="Index of execution idea to use")
    parser.add_argument("--execute", action="store_true", help="Execute trade (requires active exchange)")
    parser.add_argument("--yes", action="store_true", help="Skip execution confirmation prompt")
    parser.add_argument("--skip-portfolio", action="store_true", help="Skip fetching live portfolio data")
    parser.add_argument("--account-state-json", help="Inline JSON for account state")
    parser.add_argument("--account-state-file", help="JSON file for account state")
    parser.add_argument("--open-positions-json", help="Inline JSON for open positions")
    parser.add_argument("--open-positions-file", help="JSON file for open positions")

    args = parser.parse_args()
    return asyncio.run(run_pipeline(args))


if __name__ == "__main__":
    raise SystemExit(main())
