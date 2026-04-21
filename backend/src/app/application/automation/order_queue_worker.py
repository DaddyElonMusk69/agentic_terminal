from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.application.automation import topics
from app.application.automation.config_service import (
    AutomationConfigService,
    DEFAULT_MAX_POSITIONS,
)
from app.application.automation.execution_mode import ExecutionMode, normalize_execution_mode, should_execute_trades
from app.application.automation.order_queue_service import OrderQueuePolicy
from app.application.auto_add.service import AutoAddService
from app.application.bus.outbox_service import OutboxService
from app.application.circuit_breaker.service import CircuitBreakerService
from app.application.pending_entry.service import PendingEntryService
from app.application.position_origin.service import PositionOriginService
from app.application.trade_executor.service import TradeExecutorService
from app.application.trade_guard.service import TradeGuardService
from app.application.portfolio.service import PortfolioService
from app.domain.llm_response_worker.models import ExecutionAction, ExecutionIdea
from app.domain.trade_executor.models import ExecutionResult
from app.infrastructure.repositories.order_queue_repository import OrderQueueRepository, OrderQueueItem


class OrderQueueWorker:
    LIMIT_ENTRY_EXECUTION_MAX_ATTEMPTS = 3
    LIMIT_ENTRY_SLOT_MULTIPLIER = 2
    LIMIT_ENTRY_RESERVATION_TTL_SECONDS = 90
    MARKET_OPEN_RESERVATION_TTL_SECONDS = 90
    _limit_entry_reservations_lock = asyncio.Lock()
    _limit_entry_reservations: dict[str, dict[str, "_LimitEntryReservation"]] = {}
    _market_open_reservations_lock = asyncio.Lock()
    _market_open_reservations: dict[str, dict[str, "_MarketOpenReservation"]] = {}

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
        auto_add_service: Optional[AutoAddService] = None,
        automation_config_service: Optional[AutomationConfigService] = None,
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
        self._auto_add_service = auto_add_service
        self._automation_config_service = automation_config_service
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
        max_positions = await self._get_max_positions()
        market_open_reservation = await self._reserve_market_open_slot_if_needed(
            decision,
            request_id=payload.get("source_request_id", item.id),
            open_positions=open_positions,
        )
        try:
            inflight_market_open_count = 0
            if market_open_reservation is not None:
                inflight_market_open_count = await self._count_inflight_market_open_reservations(
                    market_open_reservation.account_id,
                    open_positions=open_positions,
                )

            guard_result = await self._trade_guard.validate(
                decision,
                account_state=account_state,
                market_data=market_data,
                open_orders=open_orders,
                open_positions=open_positions,
                pending_entries=pending_entries,
                price_fetcher=price_fetcher,
                max_positions=max_positions,
                inflight_market_open_count=inflight_market_open_count,
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

            execution_result, execution_attempts, retry_errors = await self._execute_with_retries(
                guarded_decision,
                request_id=payload.get("source_request_id", item.id),
                session_id=session_id,
                cycle_number=cycle_number,
                execution_mode=execution_mode.value,
                open_positions=open_positions,
            )
            result_payload = dict(execution_result.__dict__)
            result_payload["retry_attempts"] = execution_attempts
            if retry_errors:
                result_payload["retry_errors"] = retry_errors

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
                await self._register_auto_add_if_needed(
                    decision=guarded_decision,
                    execution_result=execution_result,
                    session_id=session_id,
                    open_positions=open_positions,
                )
                await self._cleanup_auto_add_if_needed(
                    decision=guarded_decision,
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
                            "retry_attempts": execution_attempts,
                            "retried": execution_attempts > 1,
                            "retry_errors": retry_errors,
                            "cycle_number": cycle_number,
                        },
                        session_id,
                    ),
                )
            else:
                final_error = execution_result.error or "execution_failed"
                await self._repository.mark_failed(item.id, final_error)
                await self._outbox.enqueue_event(
                    topics.TRADE_FAILED,
                    _with_session(
                        {
                            "request_id": item.id,
                            "error": final_error,
                            "result": result_payload,
                            "execution_idea": idea_payload,
                            "final_order": final_order,
                            "retry_attempts": execution_attempts,
                            "retried": execution_attempts > 1,
                            "retry_errors": retry_errors,
                            "cycle_number": cycle_number,
                        },
                        session_id,
                    ),
                )

            return True
        finally:
            if market_open_reservation is not None:
                await self._release_market_open_reservation(market_open_reservation)

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
        if not symbol:
            return

        status = getattr(execution_result, "status", None)
        if action in _OPEN_ACTIONS or action == ExecutionAction.CLOSE.value:
            if not _is_filled_status(status):
                return
        elif not getattr(execution_result, "success", False):
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
                    stop_loss_roe=_safe_float(final_order.get("stop_loss_roe")),
                    take_profit_roe=_safe_float(final_order.get("take_profit_roe")),
                )
            except Exception:
                return
            return

        if action == ExecutionAction.UPDATE_SL.value:
            try:
                await self._position_origin_service.upsert(
                    account_id=account.id,
                    symbol=symbol,
                    stop_loss_roe=_safe_float(final_order.get("stop_loss_roe")),
                )
            except Exception:
                return
            return

        if action == ExecutionAction.UPDATE_TP.value:
            try:
                await self._position_origin_service.upsert(
                    account_id=account.id,
                    symbol=symbol,
                    take_profit_roe=_safe_float(final_order.get("take_profit_roe")),
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

    async def _reserve_market_open_slot_if_needed(
        self,
        decision: ExecutionIdea,
        *,
        request_id: str,
        open_positions: Optional[list],
    ) -> "_MarketOpenReservation | None":
        if decision.action not in _MARKET_OPEN_ACTIONS:
            return None
        if _position_exists_before_execution(open_positions, decision.symbol):
            return None

        account_id = await self._get_active_account_id()
        if not account_id:
            return None

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=self.MARKET_OPEN_RESERVATION_TTL_SECONDS)

        async with self._market_open_reservations_lock:
            reservations = self._market_open_reservations.setdefault(account_id, {})
            _prune_expired_market_open_reservations(reservations, now)
            existing = reservations.get(request_id)
            if existing is not None:
                return existing

            reservation = _MarketOpenReservation(
                account_id=account_id,
                request_id=request_id,
                symbol=_normalize_symbol(decision.symbol),
                expires_at=expires_at,
            )
            reservations[request_id] = reservation
            return reservation

    async def _count_inflight_market_open_reservations(
        self,
        account_id: str,
        *,
        open_positions: Optional[list],
    ) -> int:
        live_symbols = _collect_open_position_symbols(open_positions)
        now = datetime.now(timezone.utc)

        async with self._market_open_reservations_lock:
            reservations = self._market_open_reservations.get(account_id)
            if reservations is None:
                return 0
            _prune_expired_market_open_reservations(reservations, now)
            if not reservations:
                self._market_open_reservations.pop(account_id, None)
                return 0
            symbols = {
                reservation.symbol
                for reservation in reservations.values()
                if reservation.symbol and reservation.symbol not in live_symbols
            }
            return len(symbols)

    async def _release_market_open_reservation(
        self,
        reservation: "_MarketOpenReservation",
    ) -> None:
        async with self._market_open_reservations_lock:
            reservations = self._market_open_reservations.get(reservation.account_id)
            if reservations is None:
                return
            reservations.pop(reservation.request_id, None)
            if not reservations:
                self._market_open_reservations.pop(reservation.account_id, None)

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

    async def _register_auto_add_if_needed(
        self,
        *,
        decision: ExecutionIdea,
        execution_result: Any,
        session_id: str | None,
        open_positions: Optional[list],
    ) -> None:
        if self._auto_add_service is None:
            return
        if decision.action not in (
            ExecutionAction.OPEN_LONG,
            ExecutionAction.OPEN_SHORT,
            ExecutionAction.OPEN_LONG_LIMIT,
            ExecutionAction.OPEN_SHORT_LIMIT,
        ):
            return
        try:
            await self._auto_add_service.register_fresh_entry(
                decision=decision,
                execution_result=execution_result,
                session_id=session_id,
                open_positions_before=open_positions,
            )
        except Exception:
            return

    async def _cleanup_auto_add_if_needed(
        self,
        *,
        decision: ExecutionIdea,
        execution_result: Any,
    ) -> None:
        if self._auto_add_service is None:
            return
        if decision.action != ExecutionAction.CLOSE:
            return
        if not _is_filled_status(getattr(execution_result, "status", None)):
            return
        try:
            await self._auto_add_service.cancel_for_symbol(
                decision.symbol,
                reason="position_closed",
            )
        except Exception:
            return

    async def _execute_with_retries(
        self,
        decision: ExecutionIdea,
        *,
        request_id: str,
        session_id: str | None,
        cycle_number: int | None,
        execution_mode: str,
        open_positions: Optional[list],
    ) -> tuple[ExecutionResult, int, list[str]]:
        max_attempts = (
            self.LIMIT_ENTRY_EXECUTION_MAX_ATTEMPTS
            if decision.action in _LIMIT_OPEN_ACTIONS
            else 1
        )

        attempt = 0
        errors: list[str] = []
        result = ExecutionResult(success=False, status="error", error="execution_not_attempted")
        reservation: _LimitEntryReservation | None = None
        try:
            while attempt < max_attempts:
                attempt += 1
                await self._cleanup_stale_limit_entries_if_needed(
                    decision,
                    request_id=request_id,
                    session_id=session_id,
                    cycle_number=cycle_number,
                    execution_mode=execution_mode,
                    attempt=attempt,
                )
                if reservation is None and decision.action in _LIMIT_OPEN_ACTIONS:
                    reservation_outcome = await self._reserve_limit_entry_slot_if_available(
                        decision,
                        request_id=request_id,
                        open_positions=open_positions,
                    )
                    if reservation_outcome.reservation is None:
                        result = ExecutionResult(
                            success=False,
                            status="invalid",
                            error=reservation_outcome.error or "limit_entry_slot_cap_reached",
                            raw_response=reservation_outcome.details,
                        )
                        return result, attempt, errors
                    reservation = reservation_outcome.reservation
                try:
                    result = await self._trade_executor.execute(decision)
                except Exception as exc:
                    result = ExecutionResult(success=False, status="error", error=str(exc))

                if result.success:
                    return result, attempt, errors

                error_text = result.error or result.status or "execution_failed"
                errors.append(error_text)
                if attempt >= max_attempts or not _is_retryable_limit_entry_failure(result):
                    return result, attempt, errors

                await self._outbox.enqueue_event(
                    topics.ORDER_MODIFIED,
                    _with_session(
                        {
                            "request_id": request_id,
                            "symbol": decision.symbol,
                            "execution_mode": execution_mode,
                            "execution_retry": {
                                "attempt": attempt,
                                "max_attempts": max_attempts,
                                "error": error_text,
                                "action": decision.action.value,
                            },
                            "cycle_number": cycle_number,
                        },
                        session_id,
                    ),
                )
        finally:
            if reservation is not None:
                await self._release_limit_entry_reservation(reservation)

        return result, attempt, errors

    async def _cleanup_stale_limit_entries_if_needed(
        self,
        decision: ExecutionIdea,
        *,
        request_id: str,
        session_id: str | None,
        cycle_number: int | None,
        execution_mode: str,
        attempt: int,
    ) -> None:
        if self._portfolio_service is None:
            return
        if decision.action not in _LIMIT_OPEN_ACTIONS:
            return

        try:
            open_orders = await self._portfolio_service.get_open_orders([decision.symbol])
        except Exception:
            return

        target_symbol = _normalize_symbol(decision.symbol)
        canceled_orders: list[dict[str, str]] = []
        canceled_ids: set[str] = set()

        for order in open_orders or []:
            if _normalize_symbol(order.get("symbol")) != target_symbol:
                continue
            if _is_protection_order(order):
                continue
            order_id = _extract_order_id(order)
            order_symbol = str(order.get("symbol") or decision.symbol)
            if not order_id:
                continue
            try:
                await self._portfolio_service.cancel_order(order_id, order_symbol)
            except Exception:
                continue
            canceled_ids.add(order_id)
            canceled_orders.append(
                {
                    "order_id": order_id,
                    "symbol": order_symbol,
                    "type": _extract_order_type(order),
                }
            )

        canceled_pending_ids: list[str] = []
        if self._pending_entry_service is not None:
            try:
                pending_entries = await self._pending_entry_service.list_active_records_for_active_account()
            except Exception:
                pending_entries = []
            for entry in pending_entries:
                if _normalize_symbol(getattr(entry, "symbol", None)) != target_symbol:
                    continue
                entry_order_id = str(getattr(entry, "exchange_order_id", "") or "")
                if canceled_ids and entry_order_id and entry_order_id not in canceled_ids:
                    continue
                try:
                    await self._pending_entry_service.cancel_pending_entry(entry.id)
                except Exception:
                    continue
                canceled_pending_ids.append(entry.id)

        if not canceled_orders and not canceled_pending_ids:
            return

        await self._outbox.enqueue_event(
            topics.ORDER_MODIFIED,
            _with_session(
                {
                    "request_id": request_id,
                    "symbol": decision.symbol,
                    "execution_mode": execution_mode,
                    "execution_cleanup": {
                        "attempt": attempt,
                        "action": decision.action.value,
                        "canceled_entry_orders": canceled_orders,
                        "canceled_pending_entries": canceled_pending_ids,
                    },
                    "cycle_number": cycle_number,
                },
                session_id,
            ),
        )

    async def _reserve_limit_entry_slot_if_available(
        self,
        decision: ExecutionIdea,
        *,
        request_id: str,
        open_positions: Optional[list],
    ) -> "_LimitEntryReservationOutcome":
        account_id = await self._get_active_account_id()
        if not account_id:
            return _LimitEntryReservationOutcome(
                reservation=None,
                error="limit_entry_slot_reservation_failed:no_active_account",
                details=None,
            )

        slot_limit = await self._get_limit_entry_slot_limit()
        pending_entries = []
        if self._pending_entry_service is not None:
            try:
                pending_entries = await self._pending_entry_service.list_active_records_for_active_account()
            except Exception:
                pending_entries = []

        open_positions_count = _count_open_positions(open_positions)
        pending_entries_count = len(pending_entries)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=self.LIMIT_ENTRY_RESERVATION_TTL_SECONDS)

        async with self._limit_entry_reservations_lock:
            reservations = self._limit_entry_reservations.setdefault(account_id, {})
            _prune_expired_limit_entry_reservations(reservations, now)
            existing = reservations.get(request_id)
            if existing is not None:
                return _LimitEntryReservationOutcome(
                    reservation=existing,
                    error=None,
                    details=None,
                )

            reservations_count = len(reservations)
            slots_used = open_positions_count + pending_entries_count + reservations_count
            if slots_used >= slot_limit:
                if not reservations:
                    self._limit_entry_reservations.pop(account_id, None)
                return _LimitEntryReservationOutcome(
                    reservation=None,
                    error=f"limit_entry_slot_cap_reached: used={slots_used} limit={slot_limit}",
                    details={
                        "slot_limit": slot_limit,
                        "slots_used": slots_used,
                        "open_positions": open_positions_count,
                        "pending_entries": pending_entries_count,
                        "inflight_limit_entries": reservations_count,
                    },
                )

            reservation = _LimitEntryReservation(
                account_id=account_id,
                request_id=request_id,
                symbol=_normalize_symbol(decision.symbol),
                expires_at=expires_at,
            )
            reservations[request_id] = reservation
            return _LimitEntryReservationOutcome(
                reservation=reservation,
                error=None,
                details=None,
            )

    async def _release_limit_entry_reservation(self, reservation: "_LimitEntryReservation") -> None:
        async with self._limit_entry_reservations_lock:
            reservations = self._limit_entry_reservations.get(reservation.account_id)
            if reservations is None:
                return
            reservations.pop(reservation.request_id, None)
            if not reservations:
                self._limit_entry_reservations.pop(reservation.account_id, None)

    async def _get_active_account_id(self) -> str | None:
        if self._portfolio_service is None:
            return None
        try:
            account = await self._portfolio_service.get_active_account()
        except Exception:
            return None
        if account is None:
            return None
        value = str(getattr(account, "id", "") or "").strip()
        return value or None

    async def _get_max_positions(self) -> int:
        max_positions = DEFAULT_MAX_POSITIONS
        if self._automation_config_service is not None:
            try:
                config = await self._automation_config_service.get_config()
            except Exception:
                config = None
            if config is not None:
                try:
                    max_positions = max(
                        1,
                        int(getattr(config, "max_positions", DEFAULT_MAX_POSITIONS)),
                    )
                except (TypeError, ValueError):
                    max_positions = DEFAULT_MAX_POSITIONS
        return max(1, max_positions)

    async def _get_limit_entry_slot_limit(self) -> int:
        max_positions = await self._get_max_positions()
        return max(1, max_positions * self.LIMIT_ENTRY_SLOT_MULTIPLIER)


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

_LIMIT_OPEN_ACTIONS = {
    ExecutionAction.OPEN_LONG_LIMIT,
    ExecutionAction.OPEN_SHORT_LIMIT,
}

_MARKET_OPEN_ACTIONS = {
    ExecutionAction.OPEN_LONG,
    ExecutionAction.OPEN_SHORT,
}


@dataclass(frozen=True)
class _LimitEntryReservation:
    account_id: str
    request_id: str
    symbol: str
    expires_at: datetime


@dataclass(frozen=True)
class _LimitEntryReservationOutcome:
    reservation: _LimitEntryReservation | None
    error: str | None
    details: dict[str, Any] | None


@dataclass(frozen=True)
class _MarketOpenReservation:
    account_id: str
    request_id: str
    symbol: str
    expires_at: datetime


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


def _count_open_positions(open_positions: Optional[list]) -> int:
    count = 0
    for position in open_positions or []:
        if not isinstance(position, dict):
            continue
        if _normalize_symbol(position.get("symbol")):
            count += 1
    return count


def _collect_open_position_symbols(open_positions: Optional[list]) -> set[str]:
    symbols: set[str] = set()
    for position in open_positions or []:
        if not isinstance(position, dict):
            continue
        symbol = _normalize_symbol(position.get("symbol"))
        if symbol:
            symbols.add(symbol)
    return symbols


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


def _is_retryable_limit_entry_failure(execution_result: ExecutionResult) -> bool:
    status = str(getattr(execution_result, "status", "") or "").strip().lower()
    if status in {"invalid", "unsupported", "no_account", "no_credentials"}:
        return False
    return True


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        normalized = float(value)
    except (TypeError, ValueError):
        return None
    return normalized


def _extract_order_id(order: dict | None) -> str | None:
    if not isinstance(order, dict):
        return None
    for candidate in (
        order.get("id"),
        order.get("orderId"),
        order.get("algoId"),
    ):
        if candidate is None:
            continue
        value = str(candidate).strip()
        if value:
            return value
    info = order.get("info") if isinstance(order.get("info"), dict) else {}
    for candidate in (info.get("orderId"), info.get("algoId"), info.get("id")):
        if candidate is None:
            continue
        value = str(candidate).strip()
        if value:
            return value
    return None


def _extract_order_type(order: dict | None) -> str:
    if not isinstance(order, dict):
        return ""
    info = order.get("info") if isinstance(order.get("info"), dict) else {}
    params = order.get("params") if isinstance(order.get("params"), dict) else {}
    return str(
        order.get("type")
        or order.get("orderType")
        or info.get("type")
        or info.get("orderType")
        or params.get("type")
        or ""
    ).lower()


def _extract_order_flag(order: dict | None, key: str) -> bool:
    if not isinstance(order, dict):
        return False
    info = order.get("info") if isinstance(order.get("info"), dict) else {}
    params = order.get("params") if isinstance(order.get("params"), dict) else {}
    for source in (order, info, params):
        if source.get(key) is True:
            return True
        value = source.get(key)
        if isinstance(value, str) and value.strip().lower() == "true":
            return True
    return False


def _is_protection_order(order: dict | None) -> bool:
    order_type = _extract_order_type(order)
    if "take_profit" in order_type or "take-profit" in order_type or order_type.startswith("tp"):
        return True
    return _extract_order_flag(order, "reduceOnly") or _extract_order_flag(order, "closePosition")


def _prune_expired_limit_entry_reservations(
    reservations: dict[str, _LimitEntryReservation],
    now: datetime,
) -> None:
    expired = [
        request_id
        for request_id, reservation in reservations.items()
        if reservation.expires_at <= now
    ]
    for request_id in expired:
        reservations.pop(request_id, None)


def _prune_expired_market_open_reservations(
    reservations: dict[str, _MarketOpenReservation],
    now: datetime,
) -> None:
    expired = [
        request_id
        for request_id, reservation in reservations.items()
        if reservation.expires_at <= now
    ]
    for request_id in expired:
        reservations.pop(request_id, None)
