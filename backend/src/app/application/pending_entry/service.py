from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from app.application.automation import topics
from app.application.automation.config_service import (
    AutomationConfigService,
    DEFAULT_PENDING_ENTRY_TIMEOUT_SECONDS,
)
from app.application.bus.outbox_service import OutboxService
from app.application.portfolio.service import PortfolioService
from app.application.position_origin.service import PositionOriginService
from app.application.trade_executor.service import TradeExecutorService
from app.domain.llm_response_worker.models import ExecutionAction, ExecutionIdea
from app.domain.pending_entry.interfaces import PendingEntryRepository
from app.domain.pending_entry.models import (
    PendingEntryRecord,
    PendingEntrySnapshot,
    PendingEntryStatus,
)


class PendingEntryService:
    POLL_INTERVAL_SECONDS = 3

    def __init__(
        self,
        repository: PendingEntryRepository,
        portfolio_service: PortfolioService,
        trade_executor: TradeExecutorService,
        automation_config_service: AutomationConfigService,
        position_origin_service: PositionOriginService | None = None,
        outbox: OutboxService | None = None,
    ) -> None:
        self._repository = repository
        self._portfolio_service = portfolio_service
        self._trade_executor = trade_executor
        self._automation_config_service = automation_config_service
        self._position_origin_service = position_origin_service
        self._outbox = outbox

    async def register_resting_entry(
        self,
        *,
        decision: ExecutionIdea,
        execution_result,
        session_id: str | None,
    ) -> PendingEntryRecord | None:
        account = await self._portfolio_service.get_active_account()
        if account is None:
            return None

        order_id = str(getattr(execution_result, "order_id", "") or "").strip()
        if not order_id:
            return None

        existing = await self._repository.get_by_exchange_order_id(account.id, order_id)
        if existing is not None:
            return existing

        payload = getattr(execution_result, "raw_response", None)
        payload_dict = payload if isinstance(payload, dict) else None
        now = _utcnow()
        timeout_seconds = await self._get_timeout_seconds()
        intended_quantity = (
            _extract_quantity(payload_dict)
            or _safe_float(getattr(execution_result, "filled_size", None))
            or _intended_quantity_from_decision(decision)
        )
        filled_quantity = _extract_filled_quantity(payload_dict) or _safe_float(
            getattr(execution_result, "filled_size", None)
        )
        record = PendingEntryRecord(
            id=str(uuid4()),
            account_id=account.id,
            session_id=session_id,
            symbol=_normalize_symbol(decision.symbol),
            exchange_symbol=_extract_exchange_symbol(payload_dict, decision.symbol),
            side=_side_from_action(decision.action),
            exchange_order_id=order_id,
            limit_price=float(decision.limit_price or 0.0),
            intended_size_usd=_safe_float(decision.position_size_usd),
            intended_quantity=intended_quantity,
            filled_quantity=filled_quantity,
            leverage=decision.leverage,
            time_in_force=decision.time_in_force,
            stop_loss_roe=decision.stop_loss_roe,
            take_profit_roe=decision.take_profit_roe,
            anchor_frame=decision.anchor_frame,
            active_tunnel=decision.active_tunnel,
            status=PendingEntryStatus.RESTING,
            placed_at=_extract_order_time(payload_dict) or now,
            expires_at=now + timedelta(seconds=timeout_seconds),
            order_payload=payload_dict,
        )
        created = await self._repository.create(record)
        await self._emit(
            topics.PENDING_ENTRY_REGISTERED,
            {
                "symbol": created.symbol,
                "side": created.side,
                "order_id": created.exchange_order_id,
                "limit_price": created.limit_price,
                "expires_at": created.expires_at.isoformat(),
            },
            session_id=created.session_id,
        )
        return created

    async def register_protection_pending_entry(
        self,
        *,
        decision: ExecutionIdea,
        execution_result,
        session_id: str | None,
    ) -> PendingEntryRecord | None:
        account = await self._portfolio_service.get_active_account()
        if account is None:
            return None

        order_id = str(getattr(execution_result, "order_id", "") or "").strip()
        if not order_id:
            return None

        existing = await self._repository.get_by_exchange_order_id(account.id, order_id)
        if existing is not None:
            return existing

        payload = _extract_entry_payload(getattr(execution_result, "raw_response", None))
        now = _utcnow()
        timeout_seconds = await self._get_timeout_seconds()
        reference_price = (
            _safe_float(getattr(execution_result, "fill_price", None))
            or decision.limit_price
            or decision.entry_price
            or _extract_average_price(payload)
            or 0.0
        )
        intended_quantity = (
            _safe_float(getattr(execution_result, "filled_size", None))
            or _extract_quantity(payload)
            or _intended_quantity_from_decision(decision)
        )
        filled_quantity = (
            _safe_float(getattr(execution_result, "filled_size", None))
            or _extract_filled_quantity(payload)
            or intended_quantity
        )
        record = PendingEntryRecord(
            id=str(uuid4()),
            account_id=account.id,
            session_id=session_id,
            symbol=_normalize_symbol(decision.symbol),
            exchange_symbol=_extract_exchange_symbol(payload, decision.symbol),
            side=_side_from_action(decision.action),
            exchange_order_id=order_id,
            limit_price=float(reference_price or 0.0),
            intended_size_usd=_safe_float(decision.position_size_usd),
            intended_quantity=intended_quantity,
            filled_quantity=filled_quantity,
            leverage=decision.leverage,
            time_in_force=decision.time_in_force,
            stop_loss_roe=decision.stop_loss_roe,
            take_profit_roe=decision.take_profit_roe,
            anchor_frame=decision.anchor_frame,
            active_tunnel=decision.active_tunnel,
            status=PendingEntryStatus.PROTECTION_PENDING,
            placed_at=_extract_order_time(payload) or now,
            expires_at=now + timedelta(seconds=timeout_seconds),
            last_reconciled_at=now,
            last_error="waiting_for_position_visibility",
            order_payload=payload,
        )
        created = await self._repository.create(record)
        await self._emit(
            topics.PENDING_ENTRY_PROTECTION_PENDING,
            {
                "symbol": created.symbol,
                "side": created.side,
                "order_id": created.exchange_order_id,
                "reason": "entry_filled_protection_retry_registered",
            },
            session_id=created.session_id,
        )
        return created

    async def list_active_snapshots_for_active_account(
        self,
        *,
        include_marks: bool = False,
    ) -> list[PendingEntrySnapshot]:
        account = await self._portfolio_service.get_active_account()
        if account is None:
            return []
        snapshots = await self._repository.list_active_snapshots(account.id)
        if not include_marks or not snapshots:
            return snapshots

        try:
            quotes = await self._portfolio_service.get_ticker_quotes(
                [snapshot.symbol for snapshot in snapshots]
            )
        except Exception:
            quotes = {}

        enriched: list[PendingEntrySnapshot] = []
        for snapshot in snapshots:
            quote = quotes.get(snapshot.symbol)
            enriched.append(
                replace(
                    snapshot,
                    current_mark=(quote.price if quote is not None else None),
                )
            )
        return enriched

    async def list_active_records_for_active_account(self) -> list[PendingEntryRecord]:
        account = await self._portfolio_service.get_active_account()
        if account is None:
            return []
        return await self._repository.list_active(account.id)

    async def has_active_pending_entry(self, symbol: str) -> bool:
        account = await self._portfolio_service.get_active_account()
        if account is None:
            return False
        rows = await self._repository.list_active_for_symbol(account.id, _normalize_symbol(symbol))
        return bool(rows)

    async def cancel_pending_entry(self, entry_id: str) -> PendingEntryRecord | None:
        record = await self._repository.get(entry_id)
        if record is None:
            return None

        position = await self._get_live_position(record.symbol)
        open_order = await self._get_open_order(record.exchange_order_id, record.symbol)
        if open_order is not None:
            await self._cancel_exchange_order(record.exchange_order_id, record.exchange_symbol)

        if position is not None:
            updated = await self._protect_position(
                record,
                position,
                final_status=PendingEntryStatus.PARTIALLY_FILLED,
            )
            return updated

        updated = await self._update_record(
            record,
            status=PendingEntryStatus.CANCELED,
            resolved_at=_utcnow(),
            last_error=None,
        )
        await self._emit(
            topics.PENDING_ENTRY_CANCELED,
            {"symbol": updated.symbol, "order_id": updated.exchange_order_id, "reason": "manual_cancel"},
            session_id=updated.session_id,
        )
        return updated

    async def poll_once(self) -> int:
        account = await self._portfolio_service.get_active_account()
        if account is None:
            return 0

        records = await self._repository.list_active(account.id)
        if not records:
            return 0

        positions = await self._get_live_positions_index()
        open_orders = await self._get_open_orders_index([record.symbol for record in records])
        handled = 0
        for record in records:
            position = positions.get(record.symbol)
            open_order = open_orders.get(record.exchange_order_id)
            updated = await self._reconcile_record(record, position=position, open_order=open_order)
            if updated:
                handled += 1
        return handled

    async def _reconcile_record(self, record: PendingEntryRecord, *, position, open_order: dict | None) -> bool:
        now = _utcnow()
        if position is not None:
            is_partial = _is_partial_fill(record, position, open_order)
            if open_order is not None:
                await self._cancel_exchange_order(record.exchange_order_id, record.exchange_symbol)
            await self._protect_position(
                record,
                position,
                final_status=(
                    PendingEntryStatus.PARTIALLY_FILLED if is_partial else PendingEntryStatus.FILLED
                ),
            )
            return True

        if record.status == PendingEntryStatus.PROTECTION_PENDING:
            order_info = await self._portfolio_service.get_order(
                record.exchange_order_id,
                record.exchange_symbol,
            )
            if _order_canceled(order_info):
                updated = await self._update_record(
                    record,
                    status=PendingEntryStatus.FAILED,
                    resolved_at=now,
                    last_reconciled_at=now,
                    last_error="protection_pending_entry_canceled",
                    order_payload=order_info,
                )
                return True

            if now >= record.expires_at:
                updated = await self._update_record(
                    record,
                    status=PendingEntryStatus.FAILED,
                    resolved_at=now,
                    last_reconciled_at=now,
                    last_error="protection_attach_timed_out",
                    order_payload=order_info or record.order_payload,
                )
                return True

            if _order_closed_with_fill(order_info):
                await self._update_record(
                    record,
                    filled_quantity=_extract_filled_quantity(order_info) or record.filled_quantity,
                    last_reconciled_at=now,
                    last_error="waiting_for_position_visibility",
                    order_payload=order_info,
                )
                return True

            if order_info is None:
                return False

        if open_order is not None:
            if now >= record.expires_at:
                order_info = await self._portfolio_service.get_order(
                    record.exchange_order_id,
                    record.exchange_symbol,
                )
                if _order_closed_with_fill(order_info):
                    await self._transition_to_protection_pending(
                        record,
                        now=now,
                        order_info=order_info,
                    )
                    return True
                if _order_canceled(order_info):
                    updated = await self._update_record(
                        record,
                        status=PendingEntryStatus.EXPIRED,
                        resolved_at=now,
                        last_reconciled_at=now,
                        last_error=None,
                        order_payload=order_info,
                    )
                    await self._emit(
                        topics.PENDING_ENTRY_EXPIRED,
                        {"symbol": updated.symbol, "order_id": updated.exchange_order_id},
                        session_id=updated.session_id,
                    )
                    return True
                await self._cancel_exchange_order(record.exchange_order_id, record.exchange_symbol)
                updated = await self._update_record(
                    record,
                    status=PendingEntryStatus.EXPIRED,
                    resolved_at=now,
                    last_reconciled_at=now,
                    last_error=None,
                )
                await self._emit(
                    topics.PENDING_ENTRY_EXPIRED,
                    {"symbol": updated.symbol, "order_id": updated.exchange_order_id},
                    session_id=updated.session_id,
                )
                return True
            filled_quantity = _extract_filled_quantity(open_order)
            if filled_quantity != record.filled_quantity or record.last_reconciled_at is None:
                await self._update_record(
                    record,
                    filled_quantity=filled_quantity,
                    last_reconciled_at=now,
                    order_payload=open_order,
                    last_error=None,
                )
                return True
            return False

        order_info = await self._portfolio_service.get_order(
            record.exchange_order_id,
            record.exchange_symbol,
        )
        if _order_closed_with_fill(order_info):
            await self._transition_to_protection_pending(
                record,
                now=now,
                order_info=order_info,
            )
            return True

        if _order_canceled(order_info):
            terminal = PendingEntryStatus.EXPIRED if now >= record.expires_at else PendingEntryStatus.CANCELED
            updated = await self._update_record(
                record,
                status=terminal,
                resolved_at=now,
                last_reconciled_at=now,
                last_error=None,
                order_payload=order_info,
            )
            topic = topics.PENDING_ENTRY_EXPIRED if terminal == PendingEntryStatus.EXPIRED else topics.PENDING_ENTRY_CANCELED
            await self._emit(
                topic,
                {"symbol": updated.symbol, "order_id": updated.exchange_order_id},
                session_id=updated.session_id,
            )
            return True

        if now >= record.expires_at:
            updated = await self._update_record(
                record,
                status=PendingEntryStatus.EXPIRED,
                resolved_at=now,
                last_reconciled_at=now,
                last_error=None,
                order_payload=order_info or record.order_payload,
            )
            await self._emit(
                topics.PENDING_ENTRY_EXPIRED,
                {"symbol": updated.symbol, "order_id": updated.exchange_order_id},
                session_id=updated.session_id,
            )
            return True

        if order_info is None:
            updated = await self._update_record(
                record,
                status=PendingEntryStatus.ORPHANED,
                resolved_at=now,
                last_reconciled_at=now,
                last_error="order_missing_from_exchange",
            )
            await self._emit(
                topics.PENDING_ENTRY_ORPHANED,
                {"symbol": updated.symbol, "order_id": updated.exchange_order_id},
                session_id=updated.session_id,
            )
            return True

        return False

    async def _protect_position(
        self,
        record: PendingEntryRecord,
        position,
        *,
        final_status: PendingEntryStatus,
    ) -> PendingEntryRecord:
        updated = await self._update_record(
            record,
            status=PendingEntryStatus.PROTECTION_PENDING,
            filled_quantity=_position_quantity(position) or record.filled_quantity,
            last_reconciled_at=_utcnow(),
            last_error=None,
        )

        direction = _normalize_direction(getattr(position, "direction", None) or updated.side)
        entry_price = _safe_float(getattr(position, "entry_price", None)) or updated.limit_price
        leverage = _safe_float(getattr(position, "leverage", None)) or float(updated.leverage or 1)
        if direction not in {"long", "short"} or entry_price <= 0 or leverage <= 0:
            return await self._update_record(
                updated,
                last_error="missing_position_context_for_protection",
            )

        if updated.stop_loss_roe is not None:
            stop_price = _calculate_initial_stop_loss_from_roe(
                risk_roe=updated.stop_loss_roe,
                entry_price=entry_price,
                leverage=leverage,
                direction=direction,
            )
            result = await self._trade_executor.execute(
                ExecutionIdea(
                    action=ExecutionAction.UPDATE_SL,
                    symbol=updated.symbol,
                    new_stop_loss=stop_price,
                )
            )
            if not result.success:
                return await self._update_record(
                    updated,
                    last_error=f"sl_attach_failed:{result.error or result.status}",
                )

        if updated.take_profit_roe is not None:
            take_profit = _calculate_take_profit_from_roe(
                target_roe=updated.take_profit_roe,
                entry_price=entry_price,
                leverage=leverage,
                direction=direction,
            )
            result = await self._trade_executor.execute(
                ExecutionIdea(
                    action=ExecutionAction.UPDATE_TP,
                    symbol=updated.symbol,
                    new_take_profit=take_profit,
                )
            )
            if not result.success:
                return await self._update_record(
                    updated,
                    last_error=f"tp_attach_failed:{result.error or result.status}",
                )

        await self._sync_position_origin(updated)
        finalized = await self._update_record(
            updated,
            status=final_status,
            resolved_at=_utcnow(),
            last_error=None,
        )
        await self._emit(
            topics.PENDING_ENTRY_PROTECTED,
            {
                "symbol": finalized.symbol,
                "order_id": finalized.exchange_order_id,
                "status": finalized.status.value,
            },
            session_id=finalized.session_id,
        )
        return finalized

    async def _sync_position_origin(self, record: PendingEntryRecord) -> None:
        if self._position_origin_service is None:
            return
        if record.anchor_frame is None and record.active_tunnel is None:
            return
        try:
            await self._position_origin_service.upsert(
                account_id=record.account_id,
                symbol=record.symbol,
                anchor_frame=record.anchor_frame,
                active_tunnel=record.active_tunnel,
            )
        except Exception:
            return

    async def _get_live_position(self, symbol: str):
        try:
            snapshot = await self._portfolio_service.get_portfolio_snapshot()
        except Exception:
            return None
        for position in snapshot.positions:
            if _normalize_symbol(position.symbol) == _normalize_symbol(symbol):
                return position
        return None

    async def _get_live_positions_index(self) -> dict[str, object]:
        try:
            snapshot = await self._portfolio_service.get_portfolio_snapshot()
        except Exception:
            return {}
        indexed: dict[str, object] = {}
        for position in snapshot.positions:
            indexed[_normalize_symbol(position.symbol)] = position
        return indexed

    async def _get_open_orders_index(self, symbols: list[str]) -> dict[str, dict]:
        unique = sorted({_normalize_symbol(symbol) for symbol in symbols if symbol})
        try:
            orders = await self._portfolio_service.get_open_orders(unique)
        except Exception:
            return {}
        indexed: dict[str, dict] = {}
        for order in orders or []:
            order_id = _extract_order_id(order)
            if not order_id:
                continue
            indexed[order_id] = order
        return indexed

    async def _get_open_order(self, order_id: str, symbol: str) -> dict | None:
        index = await self._get_open_orders_index([symbol])
        return index.get(order_id)

    async def _cancel_exchange_order(self, order_id: str, symbol: str) -> None:
        try:
            await self._portfolio_service.cancel_order(order_id, symbol)
        except Exception:
            return

    async def _get_timeout_seconds(self) -> int:
        try:
            config = await self._automation_config_service.get_config()
        except Exception:
            return DEFAULT_PENDING_ENTRY_TIMEOUT_SECONDS
        value = getattr(config, "pending_entry_timeout_seconds", None)
        if not isinstance(value, int):
            return DEFAULT_PENDING_ENTRY_TIMEOUT_SECONDS
        return value

    async def _update_record(self, record: PendingEntryRecord, **changes) -> PendingEntryRecord:
        updated = replace(record, **changes)
        return await self._repository.update(updated)

    async def _transition_to_protection_pending(
        self,
        record: PendingEntryRecord,
        *,
        now: datetime,
        order_info: dict | None,
    ) -> PendingEntryRecord:
        protection_expiry = now + timedelta(seconds=await self._get_timeout_seconds())
        updated = await self._update_record(
            record,
            status=PendingEntryStatus.PROTECTION_PENDING,
            filled_quantity=_extract_filled_quantity(order_info) or record.filled_quantity,
            last_reconciled_at=now,
            last_error="waiting_for_position_visibility",
            order_payload=order_info,
            expires_at=protection_expiry,
        )
        await self._emit(
            topics.PENDING_ENTRY_PROTECTION_PENDING,
            {"symbol": updated.symbol, "order_id": updated.exchange_order_id},
            session_id=updated.session_id,
        )
        return updated

    async def _emit(self, topic: str, payload: dict, *, session_id: str | None) -> None:
        if self._outbox is None:
            return
        event = dict(payload)
        if session_id:
            event["session_id"] = session_id
        await self._outbox.enqueue_event(topic, event)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_symbol(value: object) -> str:
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


def _normalize_direction(value: object) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"buy", "long"}:
        return "long"
    if raw in {"sell", "short"}:
        return "short"
    return raw


def _side_from_action(action: ExecutionAction) -> str:
    if action in (ExecutionAction.OPEN_SHORT, ExecutionAction.OPEN_SHORT_LIMIT):
        return "SHORT"
    return "LONG"


def _extract_exchange_symbol(payload: dict | None, fallback: str) -> str:
    if isinstance(payload, dict):
        symbol = payload.get("symbol")
        if isinstance(symbol, str) and symbol.strip():
            return symbol.strip()
    return fallback


def _extract_order_id(order: dict | None) -> str:
    if not isinstance(order, dict):
        return ""
    for key in ("id", "orderId", "algoId"):
        value = order.get(key)
        if value:
            return str(value)
    info = order.get("info") if isinstance(order.get("info"), dict) else {}
    for key in ("orderId", "algoId"):
        value = info.get(key)
        if value:
            return str(value)
    return ""


def _extract_order_time(payload: dict | None) -> datetime | None:
    if not isinstance(payload, dict):
        return None
    for key in ("timestamp", "updateTime", "transactTime"):
        value = _safe_float(payload.get(key))
        if value and value > 0:
            return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)
    info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
    for key in ("updateTime", "time", "transactTime"):
        value = _safe_float(info.get(key))
        if value and value > 0:
            return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)
    return None


def _extract_average_price(payload: dict | None) -> float | None:
    if not isinstance(payload, dict):
        return None
    for key in ("average", "avgPrice", "price"):
        value = _safe_float(payload.get(key))
        if value and value > 0:
            return value
    info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
    for key in ("avgPrice", "averagePrice", "price"):
        value = _safe_float(info.get(key))
        if value and value > 0:
            return value
    return None


def _extract_entry_payload(payload: object) -> dict | None:
    if not isinstance(payload, dict):
        return None
    entry_payload = payload.get("entry_order")
    if isinstance(entry_payload, dict):
        return entry_payload
    return payload


def _extract_quantity(payload: dict | None) -> float | None:
    if not isinstance(payload, dict):
        return None
    for key in ("amount", "origQty", "quantity"):
        value = _safe_float(payload.get(key))
        if value and value > 0:
            return value
    info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
    for key in ("origQty", "qty", "quantity"):
        value = _safe_float(info.get(key))
        if value and value > 0:
            return value
    return None


def _extract_filled_quantity(payload: dict | None) -> float | None:
    if not isinstance(payload, dict):
        return None
    for key in ("filled", "executedQty"):
        value = _safe_float(payload.get(key))
        if value is not None:
            return value
    info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
    for key in ("executedQty", "cumQty"):
        value = _safe_float(info.get(key))
        if value is not None:
            return value
    return None


def _intended_quantity_from_decision(decision: ExecutionIdea) -> float | None:
    if decision.position_size_usd is None or decision.limit_price is None or decision.limit_price <= 0:
        return None
    return decision.position_size_usd / decision.limit_price


def _safe_float(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _position_quantity(position) -> float | None:
    return abs(_safe_float(getattr(position, "size", None)) or 0.0) or None


def _is_partial_fill(record: PendingEntryRecord, position, open_order: dict | None) -> bool:
    if open_order is not None:
        return True
    intended = record.intended_quantity
    filled = _position_quantity(position)
    if intended is None or intended <= 0 or filled is None:
        return False
    return filled + max(1e-8, intended * 0.001) < intended


def _order_closed_with_fill(order: dict | None) -> bool:
    status = str((order or {}).get("status") or "").strip().lower()
    if status in {"closed", "filled"}:
        return (_extract_filled_quantity(order) or 0.0) > 0
    return False


def _order_canceled(order: dict | None) -> bool:
    status = str((order or {}).get("status") or "").strip().lower()
    return status in {"canceled", "cancelled", "expired", "rejected"}


def _calculate_initial_stop_loss_from_roe(
    *,
    risk_roe: float,
    entry_price: float,
    leverage: float,
    direction: str,
) -> float:
    normalized_roe = abs(float(risk_roe))
    if direction == "long":
        stop_price = entry_price * (1 - (normalized_roe / leverage))
    else:
        stop_price = entry_price * (1 + (normalized_roe / leverage))
    return float(f"{stop_price:.5g}")


def _calculate_take_profit_from_roe(
    *,
    target_roe: float,
    entry_price: float,
    leverage: float,
    direction: str,
) -> float:
    if direction == "long":
        take_profit = entry_price * (1 + (target_roe / leverage))
    else:
        take_profit = entry_price * (1 - (target_roe / leverage))
    return float(f"{take_profit:.5g}")
