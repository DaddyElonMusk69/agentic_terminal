#!/usr/bin/env python3
"""
Pipeline test script: parse LLM response -> trade guard -> circuit breaker -> trade execution.

Usage examples:
  python backend/scripts/pipeline_test.py --response-file /tmp/llm_response.txt
  python backend/scripts/pipeline_test.py --response-file /tmp/llm_response.txt --execute

If you don't pass --response/--response-file, paste the response into LLM_RESPONSE below.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]
SYS_PATH = str(ROOT / "src")
if SYS_PATH not in sys.path:
    sys.path.append(SYS_PATH)

from app.application.llm_response_worker.service import LlmResponseWorker
from app.application.trade_guard.dependencies import get_trade_guard_service
from app.application.circuit_breaker.dependencies import get_circuit_breaker_service
from app.application.trade_executor.dependencies import get_trade_executor_service
from app.application.portfolio.dependencies import get_portfolio_service
from app.domain.llm_response_worker.models import ExecutionIdea


LLM_RESPONSE = """
## Step 1: Natural Language Analysis
- Dominant timeframe is `12h` (highest interval with tunnel interaction), so it sets the bias.
- On `12h`, price is sitting **slightly above to overlapping the fast tunnel (36/44)** and holding a shallow upward slope; **medium tunnel (144/169) is still overhead**, so this is an early reclaim/bounce attempt rather than a clean trend breakout.
- On `4h`, price is **chopping near/just below the fast tunnel**, so lower-TF motion quality is mixed (not strong momentum yet), but it does not override the `12h` bias.
- Quant context: `12h` OI slope is strongly positive (supports potential directional expansion), while CVD/netflow are negative (keeps this in **probe** sizing).

- Verdict: **Weak Buy**
- Confidence: **58%**

## Step 2. JSON Server Actions:
JSON_ARRAY
[{
  "action": "OPEN_LONG",
  "symbol": "AT",
  "tier": 3,
  "stop_loss": 0.151,
  "leverage": 1,
  "take_profit_roe": 0.12,
  "confidence": 58,
  "reasoning": "Dominant 12h shows price slightly above/overlapping the fast EMA tunnel (36/44) with mild upward slope, consistent with an early reclaim/bounce attempt. 4h is still messy/overlapping so size is kept to a probe tier. Stop is placed below the recent swing/tunnel shelf to define risk; target expresses upside expansion without requiring full 12h confirmation.",
  "execute": true
}]

## Step 3. JSON Considerations:
JSON_CONSIDER
[{
  "symbol": "AT",
  "reasoning": "Multi-timeframe (12h+4h) tunnel resonance with price basing around the fast tunnel; 12h bias is mildly constructive while 4h is still noisy, making AT a good candidate for a small exploratory long that can be tiered up only if price accepts above the tunnel and starts traveling.",
  "recommend_action": "OPEN_LONG"
}]
"""


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


async def run_pipeline(args: argparse.Namespace) -> int:
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

    guard_service = get_trade_guard_service()
    guard_result = await guard_service.validate(
        decision,
        account_state=account_state,
        open_positions=open_positions,
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

    executor = get_trade_executor_service()
    exec_result = await executor.execute(guarded_decision)
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
    parser.add_argument("--skip-portfolio", action="store_true", help="Skip fetching live portfolio data")
    parser.add_argument("--account-state-json", help="Inline JSON for account state")
    parser.add_argument("--account-state-file", help="JSON file for account state")
    parser.add_argument("--open-positions-json", help="Inline JSON for open positions")
    parser.add_argument("--open-positions-file", help="JSON file for open positions")

    args = parser.parse_args()
    return asyncio.run(run_pipeline(args))


if __name__ == "__main__":
    raise SystemExit(main())
