from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.application.automation import topics
from app.domain.automation_history.interfaces import (
    AutomationLogRepository,
    AutomationSessionRepository,
    AutomationTradeRepository,
)
from app.domain.automation_history.models import (
    AutomationLogRecord,
    AutomationSessionRecord,
    AutomationTradeRecord,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AutomationHistoryService:
    def __init__(
        self,
        session_repo: AutomationSessionRepository,
        log_repo: AutomationLogRepository,
        trade_repo: AutomationTradeRepository,
    ) -> None:
        self._sessions = session_repo
        self._logs = log_repo
        self._trades = trade_repo

    async def start_session(
        self,
        session_id: str,
        execution_mode: str,
        provider: Optional[str],
        model: Optional[str],
        config_snapshot: Optional[dict],
    ) -> AutomationSessionRecord:
        existing = await self._sessions.get_by_id(session_id)
        if existing is not None:
            return existing
        return await self._sessions.create_session(
            session_id=session_id,
            execution_mode=execution_mode,
            provider=provider,
            model=model,
            config_snapshot=config_snapshot,
        )

    async def end_session(
        self,
        session_id: str,
        total_cycles: int,
    ) -> Optional[AutomationSessionRecord]:
        session = await self._sessions.get_by_id(session_id)
        if session is None:
            return None
        total_trades = await self._trades.count_by_session(session_id)
        total_pnl = await self._trades.sum_pnl_by_session(session_id)
        return await self._sessions.end_session(
            session_id=session_id,
            ended_at=_utcnow(),
            total_cycles=total_cycles,
            total_trades=total_trades,
            total_pnl=total_pnl,
        )

    async def record_event(self, topic: str, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        session_id = _extract_session_id(payload)
        if not session_id:
            return

        if topic == topics.PROMPT_REQUESTED:
            await self._sessions.increment_prompt_count(session_id, 1)

        if _should_log_topic(topic, payload):
            log_type = _resolve_log_type(topic)
            cycle_number = _extract_cycle_number(payload)
            log_payload = dict(payload)
            log_payload.setdefault("event_type", topic)
            await self._logs.create_log(
                session_id=session_id,
                log_type=log_type,
                data=log_payload,
                cycle_number=cycle_number,
            )

        if topic in {topics.TRADE_EXECUTED, topics.TRADE_FAILED}:
            trade_payload = _build_trade_payload(topic, payload)
            if trade_payload is not None:
                await self._trades.create_trade(
                    session_id=session_id,
                    **trade_payload,
                )

    async def sync_external_trades(
        self,
        session_id: str,
        trades: list[dict],
        cycle_number: int = 0,
    ) -> int:
        if not session_id or not isinstance(trades, list) or not trades:
            return 0

        existing_order_ids = await self._trades.list_order_ids_by_session(session_id)
        created = 0

        for trade in trades:
            payload = _build_external_trade_payload(trade, cycle_number=cycle_number)
            if payload is None:
                continue
            order_id = payload.get("order_id")
            if not isinstance(order_id, str) or not order_id.strip():
                continue
            if order_id in existing_order_ids:
                continue
            await self._trades.create_trade(session_id=session_id, **payload)
            existing_order_ids.add(order_id)
            created += 1

        return created

    async def reconcile_external_trades(
        self,
        session_id: str,
        trades: list[dict],
        cycle_number: int = 0,
        started_at: Optional[datetime] = None,
        ended_at: Optional[datetime] = None,
        match_window_seconds: int = 300,
    ) -> dict[str, int]:
        summary = {
            "scanned": 0,
            "in_window": 0,
            "matched": 0,
            "updated": 0,
            "created": 0,
        }
        if not session_id or not isinstance(trades, list) or not trades:
            return summary

        session = await self._sessions.get_by_id(session_id)
        window_start = _to_utc(started_at) or (session.started_at if session else None)
        window_end = _to_utc(ended_at) or _utcnow()
        if window_start and window_end and window_end < window_start:
            window_start, window_end = window_end, window_start

        session_trades = await self._trades.list_by_session(session_id)
        known_order_ids = {
            canonical
            for canonical in (
                _canonical_order_id(order_id)
                for order_id in await self._trades.list_order_ids_by_session(session_id)
            )
            if canonical
        }

        local_by_order: dict[str, list[AutomationTradeRecord]] = {}
        local_close_by_symbol: dict[str, list[AutomationTradeRecord]] = {}
        for trade in session_trades:
            canonical = _canonical_order_id(trade.order_id)
            if canonical:
                local_by_order.setdefault(canonical, []).append(trade)
            symbol = (trade.symbol or "").upper()
            if symbol and _is_close_action(trade.action):
                local_close_by_symbol.setdefault(symbol, []).append(trade)

        matched_trade_ids: set[int] = set()

        for trade in trades:
            summary["scanned"] += 1
            payload = _build_external_trade_payload(trade, cycle_number=cycle_number)
            if payload is None:
                continue

            closed_at = payload.get("closed_at")
            if not _is_within_bounds(closed_at, start=window_start, end=window_end):
                continue
            summary["in_window"] += 1

            order_id = payload.get("order_id")
            canonical_order = _canonical_order_id(order_id)

            matched = None
            if canonical_order:
                matched = _pick_unmatched_trade(
                    local_by_order.get(canonical_order, []),
                    matched_trade_ids,
                )

            if matched is None:
                symbol = str(payload.get("symbol") or "").upper()
                matched = _match_local_close_trade(
                    local_close_by_symbol.get(symbol, []),
                    external_closed_at=closed_at,
                    matched_trade_ids=matched_trade_ids,
                    window_seconds=match_window_seconds,
                )

            if matched is not None:
                summary["matched"] += 1
                matched_trade_ids.add(matched.id)
                updates = _build_reconciliation_updates(matched, payload)
                if updates:
                    await self._trades.update_trade(matched.id, updates)
                    summary["updated"] += 1
                    updated_order = updates.get("order_id")
                    updated_canonical = _canonical_order_id(updated_order)
                    if updated_canonical:
                        known_order_ids.add(updated_canonical)
                continue

            if canonical_order and canonical_order in known_order_ids:
                continue

            await self._trades.create_trade(session_id=session_id, **payload)
            summary["created"] += 1
            if canonical_order:
                known_order_ids.add(canonical_order)

        return summary

    async def list_sessions(
        self,
        limit: int,
        offset: int,
    ) -> tuple[list[AutomationSessionRecord], int]:
        sessions = await self._sessions.list_all(limit=limit, offset=offset)
        total = await self._sessions.count_all()
        return sessions, total

    async def get_session(self, session_id: str) -> Optional[AutomationSessionRecord]:
        return await self._sessions.get_by_id(session_id)

    async def get_session_detail(
        self,
        session_id: str,
        log_limit: int = 1000,
        log_offset: int = 0,
    ) -> tuple[Optional[AutomationSessionRecord], list[AutomationLogRecord], list[AutomationTradeRecord]]:
        session = await self._sessions.get_by_id(session_id)
        if session is None:
            return None, [], []
        logs = await self._logs.list_by_session(session_id, limit=log_limit, offset=log_offset)
        trades = await self._trades.list_by_session(session_id)
        return session, logs, trades

    async def get_session_detail_all(
        self,
        session_id: str,
        log_batch_size: int = 1000,
    ) -> tuple[Optional[AutomationSessionRecord], list[AutomationLogRecord], list[AutomationTradeRecord]]:
        session = await self._sessions.get_by_id(session_id)
        if session is None:
            return None, [], []
        logs = await self._list_all_logs(session_id, log_batch_size)
        trades = await self._trades.list_by_session(session_id)
        return session, logs, trades

    async def _list_all_logs(
        self,
        session_id: str,
        batch_size: int,
    ) -> list[AutomationLogRecord]:
        logs: list[AutomationLogRecord] = []
        offset = 0
        safe_batch = max(1, int(batch_size))
        while True:
            batch = await self._logs.list_by_session(
                session_id,
                limit=safe_batch,
                offset=offset,
            )
            if not batch:
                break
            logs.extend(batch)
            if len(batch) < safe_batch:
                break
            offset += safe_batch
        return logs

    async def delete_session(self, session_id: str) -> bool:
        await self._trades.delete_by_session(session_id)
        await self._logs.delete_by_session(session_id)
        return await self._sessions.delete_session(session_id)


def _extract_session_id(payload: dict) -> Optional[str]:
    session_id = payload.get("session_id")
    if isinstance(session_id, str) and session_id.strip():
        return session_id
    return None


def _extract_cycle_number(payload: dict) -> int:
    value = payload.get("cycle_number")
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _should_log_topic(topic: str, payload: dict) -> bool:
    if topic.startswith("automation.") or topic.startswith("trade."):
        return True
    if topic == "scanner.ema.log":
        event = payload.get("event")
        return event in {
            "scan_init",
            "scan_config",
            "scan_finished",
            "state_processed",
            "scan_empty_config",
            "scan_error",
        }
    if topic == "scanner.quant.log":
        log_type = payload.get("type")
        message = payload.get("message") if isinstance(payload.get("message"), str) else ""
        if log_type in {"cycle-start", "cycle-end", "error"}:
            return True
        if log_type == "info":
            return message.startswith("Quant config") or message.startswith("Results:")
    return False


def _resolve_log_type(topic: str) -> str:
    if topic == "scanner.ema.state":
        return "state"
    if topic.startswith("scanner."):
        return "scanner"
    if topic.startswith("automation.prompt"):
        return "prompt"
    if topic.startswith("automation.parser"):
        return "parser"
    if topic.startswith("automation.llm"):
        return "llm"
    if topic.startswith("automation.guard"):
        return "guard"
    if topic.startswith("automation.circuit"):
        return "circuit"
    if topic.startswith("trade."):
        return "execution"
    if topic.startswith("automation.order"):
        return "execution"
    return "system"


def _build_trade_payload(topic: str, payload: dict) -> Optional[dict]:
    result = payload.get("result")
    if not isinstance(result, dict):
        result = {}

    idea = payload.get("final_order")
    if not isinstance(idea, dict):
        idea = payload.get("execution_idea")
    if not isinstance(idea, dict):
        idea = {}

    symbol = idea.get("symbol") or payload.get("symbol")
    if not isinstance(symbol, str) or not symbol.strip():
        return None
    symbol = symbol.strip().upper()

    action = idea.get("action")
    action_str = str(action).upper() if action is not None else None
    direction = _action_direction(action_str)

    raw_response = result.get("raw_response") if isinstance(result.get("raw_response"), dict) else {}
    raw_info = raw_response.get("info") if isinstance(raw_response.get("info"), dict) else {}

    size_usd = _first_float(idea.get("position_size_usd"), idea.get("size_usd"))
    entry_price = _safe_float(idea.get("entry_price"))
    fill_price = _safe_float(result.get("fill_price"))
    pnl = _first_float(
        result.get("realized_pnl"),
        result.get("pnl"),
        raw_info.get("realizedPnl"),
        raw_info.get("closedPnl"),
        raw_response.get("realizedPnl"),
        raw_response.get("closedPnl"),
    )
    pnl_pct = _safe_float(result.get("pnl_pct"))
    status = result.get("status") or ("filled" if topic == topics.TRADE_EXECUTED else "failed")
    order_id = (
        result.get("order_id")
        or raw_response.get("id")
        or raw_info.get("orderId")
        or raw_info.get("order_id")
    )

    is_close = action_str in {"CLOSE", "REDUCE"} if action_str else False
    if is_close:
        exit_price = fill_price if fill_price is not None else _safe_float(idea.get("exit_price"))
        final_entry = entry_price
    else:
        final_entry = fill_price if fill_price is not None else entry_price
        exit_price = None

    closed_at = None
    if topic == topics.TRADE_EXECUTED and is_close and str(status).lower() in {"filled", "closed", "done"}:
        closed_at = _utcnow()

    return {
        "symbol": symbol,
        "direction": direction,
        "action": action_str,
        "entry_price": final_entry,
        "exit_price": exit_price,
        "size_usd": size_usd,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "status": str(status) if status is not None else None,
        "closed_at": closed_at,
        "signal_data": idea or None,
        "llm_reasoning": idea.get("reasoning") if isinstance(idea, dict) else None,
        "llm_response_full": None,
        "order_id": str(order_id) if order_id is not None else None,
        "fill_price": fill_price,
        "cycle_number": _extract_cycle_number(payload),
    }


def _action_direction(action: Optional[str]) -> Optional[str]:
    if not action:
        return None
    if "LONG" in action:
        return "LONG"
    if "SHORT" in action:
        return "SHORT"
    return None


def _safe_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_float(*values) -> Optional[float]:
    for value in values:
        parsed = _safe_float(value)
        if parsed is not None:
            return parsed
    return None


def _build_external_trade_payload(trade: dict, cycle_number: int = 0) -> Optional[dict]:
    if not isinstance(trade, dict):
        return None

    symbol = _normalize_trade_symbol(trade.get("symbol"))
    if not symbol:
        return None

    pnl = _safe_float(trade.get("pnl"))
    pnl_pct = _first_float(trade.get("pnl_pct"), trade.get("roi_pct"))
    entry_price = _safe_float(trade.get("entry_price"))
    exit_price = _safe_float(trade.get("exit_price"))
    size_usd = _first_float(trade.get("size_usd"), trade.get("position_size_usd"))
    closed_at = _parse_trade_time(trade.get("exit_time"))
    direction = _normalize_direction(trade.get("direction"))
    order_id = _build_external_order_id(trade, symbol, closed_at, pnl, exit_price)

    if order_id is None:
        return None

    return {
        "symbol": symbol,
        "direction": direction,
        "action": "CLOSE_SYNC",
        "entry_price": entry_price,
        "exit_price": exit_price,
        "size_usd": size_usd,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "status": "filled",
        "closed_at": closed_at,
        "signal_data": {
            "source": "exchange_sync",
            "trade": {
                "symbol": symbol,
                "direction": direction,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "size_usd": size_usd,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "exit_time": trade.get("exit_time"),
            },
        },
        "llm_reasoning": "exchange_sync",
        "llm_response_full": None,
        "order_id": order_id,
        "fill_price": exit_price,
        "cycle_number": int(cycle_number),
    }


def _normalize_trade_symbol(value) -> Optional[str]:
    if not isinstance(value, str):
        return None
    symbol = value.strip().upper()
    if not symbol:
        return None
    if ":" in symbol:
        symbol = symbol.split(":", 1)[0]
    if "/" in symbol:
        symbol = symbol.split("/", 1)[0]
    for suffix in ("USDT", "USDC", "BUSD", "USD"):
        if symbol.endswith(suffix) and len(symbol) > len(suffix):
            symbol = symbol[: -len(suffix)]
            break
    return symbol or None


def _normalize_direction(value) -> Optional[str]:
    if not isinstance(value, str):
        return None
    direction = value.strip().upper()
    if direction in {"LONG", "SHORT"}:
        return direction
    return None


def _parse_trade_time(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)):
        timestamp = float(value)
        # Heuristic: milliseconds if very large.
        if timestamp > 1_000_000_000_000:
            timestamp /= 1000.0
        try:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            return None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            try:
                numeric = float(raw)
                return _parse_trade_time(numeric)
            except ValueError:
                return None
    return None


def _build_external_order_id(
    trade: dict,
    symbol: str,
    closed_at: Optional[datetime],
    pnl: Optional[float],
    exit_price: Optional[float],
) -> Optional[str]:
    direct = (
        trade.get("order_id")
        or trade.get("id")
        or trade.get("trade_id")
        or trade.get("tradeId")
    )
    if direct is not None and str(direct).strip():
        return f"external:{str(direct).strip()}"

    close_marker = int(closed_at.timestamp()) if closed_at is not None else 0
    pnl_marker = "na" if pnl is None else f"{pnl:.10g}"
    price_marker = "na" if exit_price is None else f"{exit_price:.10g}"
    if not symbol:
        return None
    return f"external:auto:{symbol}:{close_marker}:{pnl_marker}:{price_marker}"


def _to_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_within_bounds(
    value: Optional[datetime],
    start: Optional[datetime],
    end: Optional[datetime],
) -> bool:
    if start is None and end is None:
        return True
    if value is None:
        return False
    value_utc = _to_utc(value)
    start_utc = _to_utc(start)
    end_utc = _to_utc(end)
    if start_utc is not None and value_utc < start_utc:
        return False
    if end_utc is not None and value_utc > end_utc:
        return False
    return True


def _canonical_order_id(order_id: Optional[str]) -> Optional[str]:
    if not isinstance(order_id, str):
        return None
    value = order_id.strip()
    if not value:
        return None
    lowered = value.lower()
    if lowered.startswith("external:"):
        value = value.split(":", 1)[1].strip()
    return value.lower() if value else None


def _is_close_action(action: Optional[str]) -> bool:
    if not isinstance(action, str):
        return False
    return action.upper() in {"CLOSE", "REDUCE", "CLOSE_SYNC"}


def _pick_unmatched_trade(
    candidates: list[AutomationTradeRecord],
    matched_trade_ids: set[int],
) -> Optional[AutomationTradeRecord]:
    for trade in candidates:
        if trade.id in matched_trade_ids:
            continue
        if _is_close_action(trade.action):
            return trade
    for trade in candidates:
        if trade.id in matched_trade_ids:
            continue
        return trade
    return None


def _match_local_close_trade(
    candidates: list[AutomationTradeRecord],
    external_closed_at: Optional[datetime],
    matched_trade_ids: set[int],
    window_seconds: int,
) -> Optional[AutomationTradeRecord]:
    if external_closed_at is None or not candidates:
        return None
    external_time = _to_utc(external_closed_at)
    ranked: list[tuple[float, AutomationTradeRecord]] = []
    for trade in candidates:
        if trade.id in matched_trade_ids:
            continue
        if trade.pnl is not None and trade.closed_at is not None and trade.exit_price is not None:
            continue
        trade_time = _to_utc(trade.closed_at or trade.created_at)
        if trade_time is None:
            continue
        delta = abs((trade_time - external_time).total_seconds())
        if delta <= max(60, int(window_seconds)):
            ranked.append((delta, trade))

    if not ranked:
        return None

    ranked.sort(key=lambda item: item[0])
    if len(ranked) > 1 and abs(ranked[1][0] - ranked[0][0]) < 30:
        return None
    return ranked[0][1]


def _build_reconciliation_updates(
    local_trade: AutomationTradeRecord,
    external_payload: dict,
) -> dict:
    updates: dict = {}

    order_id = external_payload.get("order_id")
    if (
        isinstance(order_id, str)
        and order_id.strip()
        and (not isinstance(local_trade.order_id, str) or not local_trade.order_id.strip())
    ):
        updates["order_id"] = order_id

    pnl = external_payload.get("pnl")
    if local_trade.pnl is None and pnl is not None:
        updates["pnl"] = pnl

    pnl_pct = external_payload.get("pnl_pct")
    if local_trade.pnl_pct is None and pnl_pct is not None:
        updates["pnl_pct"] = pnl_pct

    exit_price = external_payload.get("exit_price")
    if local_trade.exit_price is None and exit_price is not None:
        updates["exit_price"] = exit_price

    fill_price = external_payload.get("fill_price")
    if local_trade.fill_price is None and fill_price is not None:
        updates["fill_price"] = fill_price

    closed_at = external_payload.get("closed_at")
    if local_trade.closed_at is None and closed_at is not None:
        updates["closed_at"] = closed_at

    status = external_payload.get("status")
    if (
        isinstance(status, str)
        and status.strip()
        and (not isinstance(local_trade.status, str) or not local_trade.status.strip())
    ):
        updates["status"] = status

    return updates
