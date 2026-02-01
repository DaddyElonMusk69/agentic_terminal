from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from app.application.automation.order_queue_service import OrderQueuePolicy
from app.application.automation import topics
from app.application.automation.execution_mode import ExecutionMode, normalize_execution_mode, should_execute_trades
from app.application.bus.outbox_service import OutboxService
from app.application.circuit_breaker.service import CircuitBreakerService
from app.application.trade_executor.service import TradeExecutorService
from app.application.trade_guard.service import TradeGuardService
from app.domain.llm_response_worker.models import ExecutionIdea
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
        policy: Optional[OrderQueuePolicy] = None,
    ) -> None:
        self._repository = repository
        self._trade_guard = trade_guard
        self._circuit_breaker = circuit_breaker
        self._trade_executor = trade_executor
        self._outbox = outbox
        self._portfolio_service = portfolio_service
        self._policy = policy or OrderQueuePolicy()

    async def process_next(self) -> bool:
        item = await self._repository.claim_next()
        if item is None:
            return False

        payload = item.payload
        session_id = payload.get("session_id")

        if _is_expired(item, self._policy):
            await self._repository.mark_dropped(item.id, "expired")
            await self._outbox.enqueue_event(
                topics.ORDER_DROPPED,
                _with_session({"request_id": item.id, "error": "expired"}, session_id),
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
                _with_session({"request_id": item.id, "error": "missing execution_idea"}, session_id),
            )
            return True

        try:
            decision = ExecutionIdea.from_dict(idea_payload)
        except Exception as exc:
            await self._repository.mark_failed(item.id, f"invalid execution_idea: {exc}")
            await self._outbox.enqueue_event(
                topics.TRADE_FAILED,
                _with_session({"request_id": item.id, "error": str(exc)}, session_id),
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
                },
                session_id,
            ),
        )

        account_state, open_positions = await self._fetch_portfolio()
        guard_result = await self._trade_guard.validate(
            decision,
            account_state=account_state,
            open_positions=open_positions,
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
                    },
                    session_id,
                ),
            )
            return True

        execution_result = await self._trade_executor.execute(guarded_decision)
        result_payload = execution_result.__dict__

        if execution_result.success:
            await self._repository.mark_done(item.id, result_payload)
            await self._outbox.enqueue_event(
                topics.TRADE_EXECUTED,
                _with_session(
                    {
                        "request_id": item.id,
                        "result": result_payload,
                        "execution_idea": idea_payload,
                        "final_order": final_order,
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
                    },
                    session_id,
                ),
            )

        return True

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
