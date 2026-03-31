from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.application.automation.order_queue_service import OrderQueuePolicy
from app.application.automation import topics
from app.application.automation.execution_mode import ExecutionMode, normalize_execution_mode, should_execute_trades
from app.application.bus.outbox_service import OutboxService
from app.application.circuit_breaker.service import CircuitBreakerService
from app.application.pending_entry.service import PendingEntryService
from app.application.trade_executor.service import TradeExecutorService
from app.application.trade_guard.service import TradeGuardService
from app.application.position_origin.service import PositionOriginService
from app.domain.llm_response_worker.models import ExecutionAction, ExecutionIdea
from app.infrastructure.repositories.order_queue_repository import OrderQueueRepository, OrderQueueItem
from app.application.portfolio.service import PortfolioService


class OrderQueueWorker:
    def __init__(
        self,
        repository: OrderQueueRepository,
        trade_guard: TradeGuardService,
        circuit_breaker: CircuitBreakerService,
        trade_executor: TradeExecutorService,
        outbox: OutboxService,
        portfolio_service: Optional[PortfolioService] = None,
        position_origin_service: Optional[PositionOriginService] = None,
        pending_entry_service: Optional[PendingEntryService] = None,
        policy: Optional[OrderQueuePolicy] = None,
    ) -> None:
        self._repository = repository
        self._trade_guard = trade_guard
        self._circuit_breaker = circuit_breaker
        self._trade_executor = trade_executor
        self._outbox = outbox
        self._portfolio_service = portfolio_service
        self._position_origin_service = position_origin_service
        self._pending_entry_service = pending_entry_service
        self._policy = policy or OrderQueuePolicy()

    async def process_next(self) -> bool:
        item = await self._repository.claim_next()
        if item is None:
            return False

        payload = item.payload
        session_id = payload.get("session_id")
        cycle_number = payload.get("cycle_number")

        if _is_expired(item, self._policy):
            await self._repository.mark_dropped(item.id, "expired")
            await self._outbox.enqueue_event(
                topics.ORDER_DROPPED,
                _with_session(
                    {"request_id": item.id, "error": "expired", "cycle_number": cycle_number},
                    session_id,
                ),
            )
            return True

        execution_mode = normalize_execution_mode(payload.get("execution_mode"))
        if execution_mode == ExecutionMode.PROMPT_TEST:
            await self._repository.mark_dropped(item.id, f"execution_mode:{execution_mode.value}")
            await self._outbox.enqueue_event(
                topics.ORDER_DROPPED,
                _with_session(
                    {
                        "request_id": payload.get("source_request_id", item.id),
                        "error": f"execution_mode:{execution_mode.value}",
                        "cycle_number": cycle_number,
                    },
                    session_id,
                ),
            )
            return True

        idea_payload = payload.get("execution_idea")
        if not isinstance(idea_payload, dict):
            await self._repository.mark_failed(item.id, "missing execution_idea")
            await self._outbox.enqueue_event(
                topics.TRADE_FAILED,
                _with_session(
                    {"request_id": item.id, "error": "missing execution_idea", "cycle_number": cycle_number},
                    session_id,
                ),
            )
            return True

        try:
            decision = ExecutionIdea.from_dict(idea_payload)
        except Exception as exc:
            await self._repository.mark_failed(item.id, f"invalid execution_idea: {exc}")
            await self._outbox.enqueue_event(
                topics.TRADE_FAILED,
                _with_session(
                    {"request_id": item.id, "error": str(exc), "cycle_number": cycle_number},
                    session_id,
                ),
            )
            return True

        await self._outbox.enqueue_event(
            topics.GUARD_STARTED,
            _with_session(
                {
                    "request_id": payload.get("source_request_id", item.id),
                    "symbol": decision.symbol,
                    "execution_mode": execution_mode.value,
                    "execution_idea": idea_payload,
                    "cycle_number": cycle_number,
                },
                session_id,
            ),
        )

        account_state, open_positions = await self._fetch_portfolio()
        market_data = await self._fetch_market_data(decision)
        price_fetcher = await self._get_price_fetcher(decision)
        pending_entries = await self._fetch_pending_entries()
        open_orders = None
        if decision.action in (ExecutionAction.UPDATE_SL, ExecutionAction.UPDATE_TP):
            open_orders = await self._fetch_open_orders(decision)
        guard_result = await self._trade_guard.validate(
            decision,
            account_state=account_state,
            market_data=market_data,
            open_orders=open_orders,
            open_positions=open_positions,
            pending_entries=pending_entries,
            price_fetcher=price_fetcher,
        )
        guard_payload = guard_result.to_dict()
        if not guard_result.is_valid:
            await self._repository.mark_failed(item.id, "trade_guard_rejected")
            await self._outbox.enqueue_event(
                topics.GUARD_REJECTED,
                _with_session(
                    {
                        "request_id": payload.get("source_request_id", item.id),
                        "symbol": decision.symbol,
                        "errors": guard_result.errors,
                        "guard": guard_payload,
                        "execution_idea": idea_payload,
                        "cycle_number": cycle_number,
                    },
                    session_id,
                ),
            )
            await self._outbox.enqueue_event(
                topics.TRADE_FAILED,
                _with_session(
                    {
                        "request_id": item.id,
                        "error": "trade_guard_rejected",
                        "details": guard_result.to_dict(),
                        "cycle_number": cycle_number,
                    },
                    session_id,
                ),
            )
            return True

        modified = [
            item.to_dict() for item in guard_result.modifications if item.modified
        ]
        final_order = (
            guard_result.decision.to_dict()
            if guard_result.decision is not None and hasattr(guard_result.decision, "to_dict")
            else idea_payload
        )
        await self._outbox.enqueue_event(
            topics.GUARD_PASSED,
            _with_session(
                {
                    "request_id": payload.get("source_request_id", item.id),
                    "symbol": decision.symbol,
                    "modifications": len(modified),
                    "warnings": guard_result.warnings,
                    "guard": guard_payload,
                    "final_order": final_order,
                    "cycle_number": cycle_number,
                },
                session_id,
            ),
        )
        if modified:
            await self._outbox.enqueue_event(
                topics.ORDER_MODIFIED,
                _with_session(
                    {
                        "symbol": decision.symbol,
                        "modifications": modified,
                        "execution_mode": execution_mode.value,
                        "cycle_number": cycle_number,
                    },
                    session_id,
                ),
            )

        guarded_decision = guard_result.decision
        breaker_result = self._circuit_breaker.evaluate(guarded_decision)
        circuit_payload = {
            "allowed": breaker_result.allowed,
            "reasons": breaker_result.reasons,
            "checked_at": breaker_result.checked_at.isoformat(),
        }
        if not breaker_result.allowed:
            await self._repository.mark_failed(item.id, "circuit_breaker_blocked")
            await self._outbox.enqueue_event(
                topics.CIRCUIT_BLOCKED,
                _with_session(
                    {
                        "request_id": payload.get("source_request_id", item.id),
                        "symbol": decision.symbol,
                        "reasons": breaker_result.reasons,
                        "circuit_breaker": circuit_payload,
                        "final_order": final_order,
                        "cycle_number": cycle_number,
                    },
                    session_id,
                ),
            )
            await self._outbox.enqueue_event(
                topics.TRADE_FAILED,
                _with_session(
                    {
                        "request_id": item.id,
                        "error": "circuit_breaker_blocked",
                        "reasons": breaker_result.reasons,
                        "cycle_number": cycle_number,
                    },
                    session_id,
                ),
            )
            return True
        await self._outbox.enqueue_event(
            topics.CIRCUIT_PASSED,
            _with_session(
                {
                    "request_id": payload.get("source_request_id", item.id),
                    "symbol": decision.symbol,
                    "circuit_breaker": circuit_payload,
                    "final_order": final_order,
                    "cycle_number": cycle_number,
                },
                session_id,
            ),
        )

        if not should_execute_trades(execution_mode):
            await self._repository.mark_dropped(item.id, f"execution_mode:{execution_mode.value}")
            await self._outbox.enqueue_event(
                topics.ORDER_DROPPED,
                _with_session(
                    {
                        "request_id": payload.get("source_request_id", item.id),
                        "error": f"execution_mode:{execution_mode.value}",
                        "guard": guard_result.to_dict(),
                        "circuit_breaker": {
                            "allowed": breaker_result.allowed,
                            "reasons": breaker_result.reasons,
                        },
                        "execution_idea": idea_payload,
                        "cycle_number": cycle_number,
                    },
                    session_id,
                ),
            )
            return True

        execution_result = await self._trade_executor.execute(guarded_decision)
        result_payload = execution_result.__dict__

        if execution_result.success:
            await self._repository.mark_done(item.id, result_payload)
            await self._register_pending_entry_if_needed(
                decision=guarded_decision,
                execution_result=execution_result,
                session_id=session_id,
                open_positions=open_positions,
            )
            await self._sync_position_origin_metadata(
                final_order=final_order,
                execution_result=execution_result,
            )
            await self._outbox.enqueue_event(
                topics.TRADE_EXECUTED,
                _with_session(
                    {
                        "request_id": item.id,
                        "result": result_payload,
                        "execution_idea": idea_payload,
                        "final_order": final_order,
                        "cycle_number": cycle_number,
                    },
                    session_id,
                ),
            )
        else:
            await self._repository.mark_failed(item.id, execution_result.error or "execution_failed")
            await self._outbox.enqueue_event(
                topics.TRADE_FAILED,
                _with_session(
                    {
                        "request_id": item.id,
                        "error": execution_result.error,
                        "result": result_payload,
                        "execution_idea": idea_payload,
                        "final_order": final_order,
                        "cycle_number": cycle_number,
                    },
                    session_id,
                ),
            )

        return True

    async def _sync_position_origin_metadata(
        self,
        *,
        final_order: dict,
        execution_result: Any,
    ) -> None:
        if self._position_origin_service is None or self._portfolio_service is None:
            return
        if not isinstance(final_order, dict):
            return

        action = str(final_order.get("action") or "").upper()
        symbol = final_order.get("symbol")
        if not symbol or not _is_filled_status(getattr(execution_result, "status", None)):
            return

        try:
            account = await self._portfolio_service.get_active_account()
        except Exception:
            return
        if account is None:
            return

        if action in _OPEN_ACTIONS:
            try:
                await self._position_origin_service.upsert(
                    account_id=account.id,
                    symbol=symbol,
                    anchor_frame=final_order.get("anchor_frame"),
                    active_tunnel=final_order.get("active_tunnel"),
                )
            except Exception:
                return
            return

        if action == ExecutionAction.CLOSE.value:
            try:
                await self._position_origin_service.delete(
                    account_id=account.id,
                    symbol=symbol,
                )
            except Exception:
                return

    async def _fetch_portfolio(self) -> tuple[Optional[dict], Optional[list]]:
        if self._portfolio_service is None:
            return None, None
        try:
            snapshot = await self._portfolio_service.get_portfolio_snapshot()
        except Exception:
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

    async def _fetch_market_data(self, decision: ExecutionIdea) -> Optional[dict]:
        if self._portfolio_service is None or not decision or not decision.symbol:
            return None
        try:
            connector = await self._portfolio_service.get_active_connector()
        except Exception:
            return None

        market_data: dict[str, Any] = {}

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

        if decision.action in (
            ExecutionAction.OPEN_LONG_LIMIT,
            ExecutionAction.OPEN_SHORT_LIMIT,
        ):
            market_data.setdefault("order_type", "limit")
        else:
            market_data.setdefault("order_type", "market")

        if not market_data:
            return None
        market_data.setdefault("exchange_name", "exchange")
        return market_data

    async def _fetch_open_orders(self, decision: ExecutionIdea) -> Optional[list]:
        if self._portfolio_service is None or not decision or not decision.symbol:
            return None
        try:
            return await self._portfolio_service.get_open_orders([decision.symbol])
        except Exception:
            return None

    async def _fetch_pending_entries(self) -> Optional[list]:
        if self._pending_entry_service is None:
            return None
        try:
            entries = await self._pending_entry_service.list_active_records_for_active_account()
        except Exception:
            return None
        return [
            {
                "id": entry.id,
                "symbol": entry.symbol,
                "side": entry.side,
                "status": entry.status.value,
                "order_id": entry.exchange_order_id,
            }
            for entry in entries
        ]

    async def _register_pending_entry_if_needed(
        self,
        *,
        decision: ExecutionIdea,
        execution_result: Any,
        session_id: str | None,
        open_positions: Optional[list],
    ) -> None:
        if self._pending_entry_service is None:
            return
        if decision.action not in (
            ExecutionAction.OPEN_LONG,
            ExecutionAction.OPEN_SHORT,
            ExecutionAction.OPEN_LONG_LIMIT,
            ExecutionAction.OPEN_SHORT_LIMIT,
        ):
            return

        status = str(getattr(execution_result, "status", "")).lower()
        try:
            if status == "resting":
                await self._pending_entry_service.register_resting_entry(
                    decision=decision,
                    execution_result=execution_result,
                    session_id=session_id,
                )
                return

            if (
                _is_filled_status(status)
                and not _position_exists_before_execution(open_positions, decision.symbol)
                and _requires_initial_protection(decision)
                and _protection_attach_needs_retry(execution_result)
            ):
                await self._pending_entry_service.register_protection_pending_entry(
                    decision=decision,
                    execution_result=execution_result,
                    session_id=session_id,
                )
        except Exception:
            return

    async def _get_price_fetcher(self, decision: ExecutionIdea) -> Optional[Any]:
        if self._portfolio_service is None or decision is None or not decision.symbol:
            return None
        try:
            connector = await self._portfolio_service.get_active_connector()
        except Exception:
            return None

        price = None
        fetcher = getattr(connector, "fetch_ticker_price", None)
        if callable(fetcher):
            try:
                price = await fetcher(decision.symbol)
            except Exception:
                return None

        if price is None or price <= 0:
            return None

        symbol = decision.symbol.upper()

        def _fetch(sym: str) -> Optional[float]:
            if not sym:
                return None
            return price if sym.upper() == symbol else None

        return _fetch


def _is_expired(item: OrderQueueItem, policy: OrderQueuePolicy) -> bool:
    now = datetime.now(timezone.utc)
    expires_at = item.expires_at
    if expires_at is None:
        expires_at = item.created_at + timedelta(minutes=policy.ttl_minutes)
    return now > expires_at


def _with_session(payload: dict, session_id: Optional[str]) -> dict:
    if session_id:
        payload = dict(payload)
        payload["session_id"] = session_id
    return payload


_OPEN_ACTIONS = {
    ExecutionAction.OPEN_LONG.value,
    ExecutionAction.OPEN_SHORT.value,
    ExecutionAction.OPEN_LONG_LIMIT.value,
    ExecutionAction.OPEN_SHORT_LIMIT.value,
}


def _is_filled_status(value: Any) -> bool:
    status = str(value or "").strip().lower()
    return status in {"filled", "closed", "done"}


def _normalize_symbol(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    symbol = value.strip().upper()
    if not symbol:
        return ""
    if ":" in symbol:
        symbol = symbol.split(":", 1)[0]
    if "/" in symbol:
        symbol = symbol.split("/", 1)[0]
    for quote in ("USDT", "USDC", "USD", "BUSD"):
        if symbol.endswith(quote) and len(symbol) > len(quote):
            return symbol[: -len(quote)]
    return symbol


def _position_exists_before_execution(open_positions: Optional[list], symbol: str) -> bool:
    target = _normalize_symbol(symbol)
    if not target:
        return False
    for position in open_positions or []:
        if not isinstance(position, dict):
            continue
        if _normalize_symbol(position.get("symbol")) == target:
            return True
    return False


def _requires_initial_protection(decision: ExecutionIdea) -> bool:
    return any(
        value is not None
        for value in (
            decision.stop_loss,
            decision.take_profit,
            decision.stop_loss_roe,
            decision.take_profit_roe,
        )
    )


def _protection_attach_needs_retry(execution_result: Any) -> bool:
    error = str(getattr(execution_result, "error", "") or "").lower()
    if "protection_attach_failed" in error or "protection_attach_partial" in error:
        return True
    payload = getattr(execution_result, "raw_response", None)
    if not isinstance(payload, dict):
        return False
    protection_status = str(payload.get("protection_status") or "").strip().lower()
    return protection_status in {"partial", "failed", "rolled_back", "error"}
