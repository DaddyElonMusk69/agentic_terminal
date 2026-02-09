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

    async def list_sessions(
        self,
        limit: int,
        offset: int,
    ) -> tuple[list[AutomationSessionRecord], int]:
        sessions = await self._sessions.list_all(limit=limit, offset=offset)
        total = await self._sessions.count_all()
        return sessions, total

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

    size_usd = _safe_float(idea.get("position_size_usd") or idea.get("size_usd"))
    entry_price = _safe_float(idea.get("entry_price"))
    fill_price = _safe_float(result.get("fill_price"))
    pnl = _safe_float(result.get("realized_pnl") or result.get("pnl"))
    pnl_pct = _safe_float(result.get("pnl_pct"))
    status = result.get("status") or ("filled" if topic == topics.TRADE_EXECUTED else "failed")
    order_id = result.get("order_id")

    is_close = action_str in {"CLOSE", "REDUCE"} if action_str else False
    if is_close:
        exit_price = fill_price or _safe_float(idea.get("exit_price"))
        final_entry = entry_price
    else:
        final_entry = fill_price or entry_price
        exit_price = None

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
        "closed_at": None,
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
