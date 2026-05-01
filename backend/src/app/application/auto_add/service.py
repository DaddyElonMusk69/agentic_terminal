from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

from app.application.automation.config_service import AutomationConfigService
from app.application.portfolio.service import PortfolioService
from app.application.trade_executor.service import TradeExecutorService
from app.application.trade_guard.service import TradeGuardService
from app.domain.auto_add.interfaces import AutoAddRepository
from app.domain.auto_add.models import (
    AutoAddPositionRecord,
    AutoAddPositionSnapshot,
    AutoAddStatus,
    AutoAddTrancheKind,
    AutoAddTrancheRecord,
    AutoAddTrancheStatus,
)
from app.domain.llm_response_worker.models import ExecutionAction, ExecutionIdea


class AutoAddService:
    POLL_INTERVAL_SECONDS = 30
    ATR_TIMEFRAME = "15m"
    ATR_PERIOD = 14
    ATR_FAILURE_RETRY_SECONDS = 15

    def __init__(
        self,
        repository: AutoAddRepository,
        portfolio_service: PortfolioService,
        trade_guard: TradeGuardService,
        trade_executor: TradeExecutorService,
        automation_config_service: AutomationConfigService,
    ) -> None:
        self._repository = repository
        self._portfolio_service = portfolio_service
        self._trade_guard = trade_guard
        self._trade_executor = trade_executor
        self._automation_config_service = automation_config_service
        self._atr_cache: dict[str, tuple[float | None, datetime]] = {}

    async def register_fresh_entry(
        self,
        *,
        decision: ExecutionIdea,
        execution_result,
        session_id: str | None,
        open_positions_before: Optional[list[dict]] = None,
    ) -> AutoAddPositionRecord | None:
        if decision.action not in {
            ExecutionAction.OPEN_LONG,
            ExecutionAction.OPEN_SHORT,
            ExecutionAction.OPEN_LONG_LIMIT,
            ExecutionAction.OPEN_SHORT_LIMIT,
        }:
            return None
        if not _is_filled_status(getattr(execution_result, "status", None)):
            return None
        if _position_exists_before_execution(open_positions_before, decision.symbol):
            return None
        config = await self._automation_config_service.get_config()
        if not config.auto_add_enabled:
            return None
        return await self._register_entry(
            symbol=decision.symbol,
            side=_side_from_action(decision.action),
            session_id=session_id,
            fill_price=(
                _safe_float(getattr(execution_result, "fill_price", None))
                or decision.limit_price
                or decision.entry_price
            ),
            initial_margin_used=_calculate_margin_from_notional(
                decision.position_size_usd,
                decision.leverage,
            ),
            leverage=_safe_float(decision.leverage),
            config=config,
        )

    async def register_limit_fill_after_protection(
        self,
        *,
        symbol: str,
        side: str,
        session_id: str | None,
    ) -> AutoAddPositionRecord | None:
        config = await self._automation_config_service.get_config()
        if not config.auto_add_enabled:
            return None
        return await self._register_entry(
            symbol=symbol,
            side=side,
            session_id=session_id,
            fill_price=None,
            initial_margin_used=None,
            leverage=None,
            config=config,
        )

    async def poll_once(self) -> int:
        account = await self._portfolio_service.get_active_account()
        if account is None:
            return 0

        records = await self._repository.list_active_positions(account.id)
        if not records:
            return 0

        try:
            live_positions = await self._portfolio_service.get_positions()
        except Exception:
            return 0
        position_index = {
            _normalize_symbol(getattr(position, "symbol", None)): position
            for position in live_positions or []
            if _is_open_position(position) and _normalize_symbol(getattr(position, "symbol", None))
        }

        open_orders_index = await self._get_open_orders_index([record.symbol for record in records])
        handled = 0
        for record in records:
            tranches = await self._repository.list_tranches(record.id)
            changed = await self._reconcile_record(
                record,
                tranches=tranches,
                live_position=position_index.get(record.symbol),
                open_orders=(open_orders_index.get(record.symbol, []) if open_orders_index is not None else None),
            )
            if changed:
                handled += 1
        return handled

    async def cancel_missing_parent_positions(self, live_symbols: list[str]) -> int:
        account = await self._portfolio_service.get_active_account()
        if account is None:
            return 0

        tracked_symbols = {
            _normalize_symbol(symbol)
            for symbol in live_symbols or []
            if _normalize_symbol(symbol)
        }
        if not tracked_symbols:
            return 0

        records = await self._repository.list_active_positions(account.id)
        if not records:
            return 0

        handled = 0
        for record in records:
            if record.symbol in tracked_symbols:
                continue
            tranches = await self._repository.list_tranches(record.id)
            await self._cancel_and_finalize(
                record,
                tranches=tranches,
                status=AutoAddStatus.CLOSED,
                reason="parent_position_closed",
            )
            handled += 1
        return handled

    async def list_position_snapshots_for_active_account(
        self,
        *,
        symbols: list[str] | None = None,
    ) -> list[AutoAddPositionSnapshot]:
        account = await self._portfolio_service.get_active_account()
        if account is None:
            return []
        if symbols:
            records = await self._repository.list_latest_positions_for_symbols(
                account.id,
                [_normalize_symbol(symbol) for symbol in symbols if _normalize_symbol(symbol)],
            )
        else:
            records = await self._repository.list_active_positions(account.id)
        if not records:
            return []

        open_orders_index = await self._get_open_orders_index([record.symbol for record in records])
        snapshots: list[AutoAddPositionSnapshot] = []
        for record in records:
            tranches = await self._repository.list_tranches(record.id)
            refreshed_record, refreshed_tranches = await self._reconcile_tranche_resolution(
                record,
                tranches=tranches,
                open_orders=(open_orders_index.get(record.symbol, []) if open_orders_index is not None else None),
            )
            snapshots.append(
                AutoAddPositionSnapshot(
                    record=refreshed_record,
                    tranches=tuple(refreshed_tranches),
                )
            )
        return snapshots

    async def cancel_for_symbol(
        self,
        symbol: str,
        *,
        reason: str,
        final_status: AutoAddStatus = AutoAddStatus.CLOSED,
    ) -> AutoAddPositionRecord | None:
        account = await self._portfolio_service.get_active_account()
        if account is None:
            return None
        normalized_symbol = _normalize_symbol(symbol)
        if not normalized_symbol:
            return None
        record = await self._repository.get_active_position_for_symbol(account.id, normalized_symbol)
        if record is None:
            return None
        tranches = await self._repository.list_tranches(record.id)
        return await self._cancel_and_finalize(record, tranches=tranches, status=final_status, reason=reason)

    async def _register_entry(
        self,
        *,
        symbol: str,
        side: str,
        session_id: str | None,
        fill_price: float | None,
        initial_margin_used: float | None,
        leverage: float | None,
        config,
    ) -> AutoAddPositionRecord | None:
        account = await self._portfolio_service.get_active_account()
        if account is None:
            return None

        normalized_symbol = _normalize_symbol(symbol)
        if not normalized_symbol:
            return None

        existing = await self._repository.get_active_position_for_symbol(account.id, normalized_symbol)
        if existing is not None:
            return existing

        live_position = await self._get_live_position(normalized_symbol)
        open_orders_index = await self._get_open_orders_index([normalized_symbol])
        open_orders = open_orders_index.get(normalized_symbol, []) if open_orders_index is not None else None
        stop_price = _extract_stop_price(open_orders, normalized_symbol) if open_orders is not None else None
        entry_price = _safe_float(getattr(live_position, "entry_price", None)) or fill_price
        quantity = _position_quantity(live_position)
        margin_used = _position_margin(live_position) or initial_margin_used
        leverage_value = _safe_float(getattr(live_position, "leverage", None)) or leverage or 1.0
        trigger_basis_price = entry_price
        original_risk_usd = _calculate_original_risk_usd(
            entry_price=entry_price,
            quantity=quantity,
            stop_price=stop_price,
            side=side,
        )
        atr_value = await self._get_latest_atr(normalized_symbol) if trigger_basis_price else None
        next_trigger_price = _calculate_ladder_trigger_price(
            side=side,
            entry_price=trigger_basis_price,
            atr_value=atr_value,
            atr_multiple=float(config.auto_add_trigger_atr_multiple),
            tranche_index=1,
        )
        status = (
            AutoAddStatus.ACTIVE
            if trigger_basis_price and margin_used and leverage_value and atr_value
            else AutoAddStatus.WAITING_PROTECTION
        )

        record = AutoAddPositionRecord(
            id=str(uuid4()),
            account_id=account.id,
            session_id=session_id,
            symbol=normalized_symbol,
            side=str(side).upper(),
            status=status,
            initial_margin_used=margin_used,
            initial_stop_price=stop_price,
            original_risk_usd=original_risk_usd,
            trigger_basis_price=trigger_basis_price,
            next_trigger_price=next_trigger_price,
            initial_entry_price=entry_price,
            initial_quantity=quantity,
            expected_quantity=quantity,
            leverage=leverage_value,
            add_count=0,
            max_tranches=int(config.auto_add_max_tranches),
            trigger_atr_multiple=float(config.auto_add_trigger_atr_multiple),
            tranche_margin_pct=float(config.auto_add_tranche_margin_pct),
            protected_stop_roe=float(getattr(config, "auto_add_protected_stop_roe", 0.0)),
            last_atr_value=atr_value,
            last_error=None if status == AutoAddStatus.ACTIVE else "waiting_for_live_position_context",
            last_capacity_blocked_at=None,
            last_trade_guard_reason=None,
            last_seen_position_size=_safe_float(getattr(live_position, "size", None)),
            last_seen_entry_price=_safe_float(getattr(live_position, "entry_price", None)),
            last_seen_mark_price=_safe_float(getattr(live_position, "mark_price", None)),
            last_seen_margin=_position_margin(live_position),
            active=True,
            resolved_at=None,
        )
        created = await self._repository.create_position(record)
        await self._ensure_initial_tranche(created)
        if status == AutoAddStatus.ACTIVE:
            armed = await self._arm_ladder(created, live_position=live_position)
            return armed or created
        return created

    async def _reconcile_record(
        self,
        record: AutoAddPositionRecord,
        *,
        tranches: list[AutoAddTrancheRecord],
        live_position,
        open_orders: list[dict] | None,
    ) -> bool:
        if live_position is None:
            await self._cancel_and_finalize(
                record,
                tranches=tranches,
                status=AutoAddStatus.CLOSED,
                reason="parent_position_closed",
            )
            return True

        if _position_conflicts_with_record(record, live_position):
            await self._cancel_and_finalize(
                record,
                tranches=tranches,
                status=AutoAddStatus.DETACHED,
                reason="position_side_changed",
            )
            return True

        if record.status == AutoAddStatus.WAITING_PROTECTION:
            updated = await self._arm_ladder(record, live_position=live_position)
            return updated is not None

        refreshed_record, refreshed_tranches = await self._reconcile_tranche_resolution(
            record,
            tranches=tranches,
            open_orders=open_orders,
            live_position=live_position,
        )
        return refreshed_record != record or refreshed_tranches != tranches

    async def _ensure_initial_tranche(self, record: AutoAddPositionRecord) -> None:
        tranches = await self._repository.list_tranches(record.id)
        if any(tranche.tranche_index == 0 for tranche in tranches):
            return
        await self._repository.create_tranche(
            AutoAddTrancheRecord(
                id=str(uuid4()),
                auto_add_position_id=record.id,
                tranche_index=0,
                kind=AutoAddTrancheKind.INITIAL,
                status=AutoAddTrancheStatus.INITIAL,
                exchange_order_id=None,
                trigger_price=None,
                fill_price=record.initial_entry_price,
                filled_quantity=record.initial_quantity,
                margin_used=record.initial_margin_used,
                position_notional_usd=_calculate_notional(record.initial_quantity, record.initial_entry_price),
                fill_time=_utcnow(),
                atr_value=record.last_atr_value,
                trigger_basis_price=record.trigger_basis_price,
                last_error=None,
            )
        )

    async def _arm_ladder(self, record: AutoAddPositionRecord, *, live_position) -> AutoAddPositionRecord | None:
        entry_price = _safe_float(getattr(live_position, "entry_price", None)) or record.initial_entry_price
        leverage = _safe_float(getattr(live_position, "leverage", None)) or record.leverage
        margin_used = _position_margin(live_position) or record.initial_margin_used
        quantity = _position_quantity(live_position) or record.initial_quantity
        open_orders_index = await self._get_open_orders_index([record.symbol])
        open_orders = open_orders_index.get(record.symbol, []) if open_orders_index is not None else None
        stop_price = (
            _extract_stop_price(open_orders, record.symbol)
            if open_orders is not None
            else record.initial_stop_price
        ) or record.initial_stop_price

        if entry_price is None or leverage is None or leverage <= 0 or margin_used is None or margin_used <= 0:
            updated = await self._maybe_update_record(
                record,
                status=AutoAddStatus.WAITING_PROTECTION,
                initial_entry_price=entry_price or record.initial_entry_price,
                leverage=leverage or record.leverage,
                initial_margin_used=margin_used or record.initial_margin_used,
                initial_quantity=quantity or record.initial_quantity,
                initial_stop_price=stop_price or record.initial_stop_price,
                last_error="waiting_for_live_position_context",
            )
            return updated

        atr_value = record.last_atr_value if record.last_atr_value is not None else await self._get_latest_atr(record.symbol)
        if atr_value is None or atr_value <= 0:
            updated = await self._maybe_update_record(
                record,
                status=AutoAddStatus.WAITING_PROTECTION,
                last_error="anchored_atr_unavailable",
            )
            return updated

        planned_margin_used = margin_used * record.tranche_margin_pct
        planned_notional = planned_margin_used * leverage
        if planned_notional <= 0:
            updated = await self._maybe_update_record(
                record,
                status=AutoAddStatus.ERROR,
                active=False,
                last_error="auto_add_target_notional_invalid",
                resolved_at=_utcnow(),
            )
            return updated

        existing_tranches = await self._repository.list_tranches(record.id)
        existing_adds = {tranche.tranche_index: tranche for tranche in existing_tranches if tranche.tranche_index > 0}
        placement_errors: list[str] = []

        for tranche_index in range(1, record.max_tranches + 1):
            existing = existing_adds.get(tranche_index)
            if existing is not None and existing.status in {
                AutoAddTrancheStatus.PLACED,
                AutoAddTrancheStatus.RESOLVED,
                AutoAddTrancheStatus.CANCELED,
            }:
                continue

            trigger_price = _calculate_ladder_trigger_price(
                side=record.side,
                entry_price=entry_price,
                atr_value=atr_value,
                atr_multiple=record.trigger_atr_multiple,
                tranche_index=tranche_index,
            )
            if trigger_price is None or trigger_price <= 0:
                placement_errors.append(f"tranche_{tranche_index}:invalid_trigger")
                continue

            result = await self._trade_executor.place_stop_market_entry(
                symbol=record.symbol,
                side="buy" if _normalize_side(record.side) == "long" else "sell",
                size_usd=planned_notional,
                trigger_price=trigger_price,
                leverage=max(1, int(round(leverage))),
            )

            tranche_record = AutoAddTrancheRecord(
                id=(existing.id if existing is not None else str(uuid4())),
                auto_add_position_id=record.id,
                tranche_index=tranche_index,
                kind=AutoAddTrancheKind.ADD,
                status=AutoAddTrancheStatus.PLACED if result.success else AutoAddTrancheStatus.FAILED,
                exchange_order_id=result.order_id if result.success else None,
                trigger_price=trigger_price,
                fill_price=None,
                filled_quantity=None,
                margin_used=planned_margin_used,
                position_notional_usd=planned_notional,
                fill_time=None,
                atr_value=atr_value,
                trigger_basis_price=entry_price,
                last_error=None if result.success else (result.error or result.status),
            )
            if existing is None:
                await self._repository.create_tranche(tranche_record)
            else:
                await self._repository.update_tranche(tranche_record)
            if not result.success:
                placement_errors.append(f"tranche_{tranche_index}:{result.error or result.status}")

        refreshed_tranches = await self._repository.list_tranches(record.id)
        next_trigger_price = _next_active_trigger_price(refreshed_tranches)
        target_status = AutoAddStatus.ACTIVE if next_trigger_price is not None else AutoAddStatus.ERROR
        updated = await self._maybe_update_record(
            record,
            status=target_status,
            active=target_status == AutoAddStatus.ACTIVE,
            initial_entry_price=entry_price,
            initial_quantity=quantity,
            initial_margin_used=margin_used,
            leverage=leverage,
            initial_stop_price=stop_price,
            trigger_basis_price=entry_price,
            next_trigger_price=next_trigger_price,
            last_atr_value=atr_value,
            last_seen_position_size=_safe_float(getattr(live_position, "size", None)),
            last_seen_entry_price=_safe_float(getattr(live_position, "entry_price", None)),
            last_seen_mark_price=_safe_float(getattr(live_position, "mark_price", None)),
            last_seen_margin=_position_margin(live_position),
            original_risk_usd=_calculate_original_risk_usd(
                entry_price=entry_price,
                quantity=quantity,
                stop_price=stop_price,
                side=record.side,
            ),
            last_error="; ".join(placement_errors) if placement_errors else None,
            resolved_at=None if target_status == AutoAddStatus.ACTIVE else _utcnow(),
        )
        return updated

    async def _reconcile_tranche_resolution(
        self,
        record: AutoAddPositionRecord,
        *,
        tranches: list[AutoAddTrancheRecord],
        open_orders: list[dict] | None,
        live_position=None,
    ) -> tuple[AutoAddPositionRecord, list[AutoAddTrancheRecord]]:
        if open_orders is None:
            return record, tranches

        open_order_ids = {
            order_id
            for order_id in (_extract_order_id(order) for order in open_orders or [])
            if order_id
        }
        refreshed_tranches = list(tranches)
        changed = False
        for idx, tranche in enumerate(refreshed_tranches):
            if tranche.kind != AutoAddTrancheKind.ADD:
                continue
            if tranche.status != AutoAddTrancheStatus.PLACED:
                continue
            if tranche.exchange_order_id and tranche.exchange_order_id not in open_order_ids:
                resolved = replace(
                    tranche,
                    status=AutoAddTrancheStatus.RESOLVED,
                    fill_time=tranche.fill_time or _utcnow(),
                    fill_price=tranche.fill_price or tranche.trigger_price,
                    last_error=None,
                )
                refreshed_tranches[idx] = await self._repository.update_tranche(resolved)
                changed = True

        resolved_count = sum(1 for tranche in refreshed_tranches if tranche.status == AutoAddTrancheStatus.RESOLVED)
        next_trigger_price = _next_active_trigger_price(refreshed_tranches)
        target_status = AutoAddStatus.ACTIVE if next_trigger_price is not None else AutoAddStatus.COMPLETED
        updated_record = await self._maybe_update_record(
            record,
            add_count=resolved_count,
            next_trigger_price=next_trigger_price,
            status=target_status,
            active=target_status == AutoAddStatus.ACTIVE,
            resolved_at=_utcnow() if target_status == AutoAddStatus.COMPLETED else None,
            last_seen_position_size=_safe_float(getattr(live_position, "size", None)) if live_position is not None else record.last_seen_position_size,
            last_seen_entry_price=_safe_float(getattr(live_position, "entry_price", None)) if live_position is not None else record.last_seen_entry_price,
            last_seen_mark_price=_safe_float(getattr(live_position, "mark_price", None)) if live_position is not None else record.last_seen_mark_price,
            last_seen_margin=_position_margin(live_position) if live_position is not None else record.last_seen_margin,
            last_error=record.last_error if target_status == AutoAddStatus.ACTIVE else None,
        )
        return updated_record or record, refreshed_tranches

    async def _cancel_and_finalize(
        self,
        record: AutoAddPositionRecord,
        *,
        tranches: list[AutoAddTrancheRecord],
        status: AutoAddStatus,
        reason: str,
    ) -> AutoAddPositionRecord:
        updated_tranches = list(tranches)
        for idx, tranche in enumerate(updated_tranches):
            if tranche.kind != AutoAddTrancheKind.ADD:
                continue
            if tranche.status != AutoAddTrancheStatus.PLACED or not tranche.exchange_order_id:
                continue
            cancel_result = await self._portfolio_service.cancel_order(tranche.exchange_order_id, record.symbol)
            canceled = replace(
                tranche,
                status=AutoAddTrancheStatus.CANCELED,
                last_error=None if cancel_result is not None else "cancel_failed_or_not_found",
            )
            updated_tranches[idx] = await self._repository.update_tranche(canceled)

        self._forget_anchored_atr(record.symbol)
        return await self._repository.update_position(
            replace(
                record,
                status=status,
                active=False,
                next_trigger_price=None,
                last_error=reason,
                resolved_at=_utcnow(),
            )
        )

    async def _maybe_update_record(self, record: AutoAddPositionRecord, **changes) -> AutoAddPositionRecord | None:
        updated = replace(record, **changes)
        if updated == record:
            return None
        return await self._repository.update_position(updated)

    async def _get_live_position(self, symbol: str):
        try:
            positions = await self._portfolio_service.get_positions()
        except Exception:
            return None
        for position in positions or []:
            if not _is_open_position(position):
                continue
            if _normalize_symbol(getattr(position, "symbol", None)) == symbol:
                return position
        return None

    async def _get_open_orders_index(self, symbols: list[str]) -> dict[str, list[dict]] | None:
        unique = sorted({_normalize_symbol(symbol) for symbol in symbols if symbol})
        if not unique:
            return {}
        try:
            orders = await self._portfolio_service.get_open_orders(unique)
        except Exception:
            return None
        index = {symbol: [] for symbol in unique}
        for order in orders or []:
            normalized_symbol = _normalize_symbol(order.get("symbol") or _extract_nested_symbol(order))
            if not normalized_symbol:
                continue
            index.setdefault(normalized_symbol, []).append(order)
        return index

    async def _get_latest_atr(self, symbol: str) -> float | None:
        now = _utcnow()
        cached = self._atr_cache.get(symbol)
        if cached is not None:
            cached_value, next_retry_at = cached
            if cached_value is not None:
                return cached_value
            if now < next_retry_at:
                return None

        try:
            candles = await self._portfolio_service.get_candles(
                symbol,
                self.ATR_TIMEFRAME,
                self.ATR_PERIOD + 1,
            )
        except Exception:
            fallback = cached[0] if cached is not None else None
            self._atr_cache[symbol] = (
                fallback,
                now + timedelta(seconds=self.ATR_FAILURE_RETRY_SECONDS),
            )
            return fallback
        if not candles or len(candles) < 2:
            fallback = cached[0] if cached is not None else None
            self._atr_cache[symbol] = (
                fallback,
                now + timedelta(seconds=self.ATR_FAILURE_RETRY_SECONDS),
            )
            return fallback

        true_ranges: list[float] = []
        previous_close = _safe_float(getattr(candles[0], "close", None))
        for candle in candles[1:]:
            high = _safe_float(getattr(candle, "high", None))
            low = _safe_float(getattr(candle, "low", None))
            close = _safe_float(getattr(candle, "close", None))
            if high is None or low is None:
                continue
            if previous_close is None:
                true_ranges.append(high - low)
            else:
                true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
            previous_close = close
        if len(true_ranges) < self.ATR_PERIOD:
            fallback = cached[0] if cached is not None else None
            self._atr_cache[symbol] = (
                fallback,
                now + timedelta(seconds=self.ATR_FAILURE_RETRY_SECONDS),
            )
            return fallback

        atr_value = sum(true_ranges[-self.ATR_PERIOD :]) / self.ATR_PERIOD
        self._atr_cache[symbol] = (atr_value, now)
        return atr_value

    def _forget_anchored_atr(self, symbol: str) -> None:
        self._atr_cache.pop(symbol, None)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _position_quantity(position) -> float | None:
    value = _safe_float(getattr(position, "size", None)) if position is not None else None
    if value is None:
        return None
    return abs(value)


def _is_open_position(position) -> bool:
    quantity = _position_quantity(position)
    if quantity is None:
        return True
    return quantity > 1e-8


def _position_margin(position) -> float | None:
    margin = _safe_float(getattr(position, "margin", None)) if position is not None else None
    if margin is not None and margin > 0:
        return margin
    entry_price = _safe_float(getattr(position, "entry_price", None)) if position is not None else None
    leverage = _safe_float(getattr(position, "leverage", None)) if position is not None else None
    quantity = _position_quantity(position)
    if entry_price is None or leverage is None or leverage <= 0 or quantity is None:
        return None
    return quantity * entry_price / leverage


def _calculate_margin_from_notional(position_size_usd: float | None, leverage: float | None) -> float | None:
    if position_size_usd is None or leverage is None or leverage <= 0:
        return None
    return position_size_usd / leverage


def _calculate_notional(quantity: float | None, price: float | None) -> float | None:
    if quantity is None or price is None:
        return None
    return quantity * price


def _side_from_action(action: ExecutionAction) -> str:
    if action in {ExecutionAction.OPEN_SHORT, ExecutionAction.OPEN_SHORT_LIMIT}:
        return "SHORT"
    return "LONG"


def _normalize_side(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"buy", "long"}:
        return "long"
    if raw in {"sell", "short"}:
        return "short"
    return raw


def _position_side(position) -> str | None:
    raw = _normalize_side(getattr(position, "direction", None))
    if raw in {"long", "short"}:
        return raw
    size = _safe_float(getattr(position, "size", None))
    if size is None:
        return None
    if size > 0:
        return "long"
    if size < 0:
        return "short"
    return None


def _is_filled_status(value: Any) -> bool:
    return str(value or "").strip().lower() in {"filled", "closed", "done"}


def _position_exists_before_execution(open_positions_before: Optional[list[dict]], symbol: str) -> bool:
    target = _normalize_symbol(symbol)
    for position in open_positions_before or []:
        if _normalize_symbol(position.get("symbol")) == target:
            return True
    return False


def _calculate_original_risk_usd(
    *,
    entry_price: float | None,
    quantity: float | None,
    stop_price: float | None,
    side: str,
) -> float | None:
    normalized_side = _normalize_side(side)
    if entry_price is None or quantity is None or stop_price is None or quantity <= 0:
        return None
    if normalized_side == "long":
        distance = entry_price - stop_price
    elif normalized_side == "short":
        distance = stop_price - entry_price
    else:
        return None
    if distance < 0:
        distance = 0.0
    return distance * quantity


def _calculate_ladder_trigger_price(
    *,
    side: str,
    entry_price: float | None,
    atr_value: float | None,
    atr_multiple: float,
    tranche_index: int,
) -> float | None:
    normalized_side = _normalize_side(side)
    if entry_price is None or atr_value is None or atr_value <= 0 or tranche_index <= 0:
        return None
    distance = atr_value * atr_multiple * tranche_index
    if normalized_side == "long":
        return entry_price + distance
    if normalized_side == "short":
        return entry_price - distance
    return None


def _extract_order_type(order: dict) -> str:
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


def _extract_trigger_price(order: dict) -> float | None:
    info = order.get("info") if isinstance(order.get("info"), dict) else {}
    params = order.get("params") if isinstance(order.get("params"), dict) else {}
    for candidate in (
        order.get("stopPrice"),
        order.get("triggerPrice"),
        order.get("triggerPx"),
        info.get("stopPrice"),
        info.get("triggerPrice"),
        info.get("triggerPx"),
        params.get("stopPrice"),
        params.get("triggerPrice"),
        params.get("triggerPx"),
        order.get("price"),
        info.get("price"),
    ):
        value = _safe_float(candidate)
        if value is not None and value > 0:
            return value
    return None


def _extract_order_id(order: dict) -> str | None:
    for candidate in (
        order.get("id"),
        order.get("orderId"),
        order.get("algoId"),
    ):
        if candidate is None:
            continue
        text = str(candidate).strip()
        if text:
            return text
    return None


def _extract_nested_symbol(order: dict) -> str | None:
    info = order.get("info") if isinstance(order.get("info"), dict) else {}
    value = order.get("symbol") or info.get("symbol")
    if isinstance(value, str) and value.strip():
        return value
    return None


def _extract_protection_prices(orders: list[dict], symbol: str) -> tuple[float | None, float | None]:
    stop_prices: list[float] = []
    take_profit_prices: list[float] = []
    target = _normalize_symbol(symbol)
    for order in orders:
        if not isinstance(order, dict):
            continue
        order_symbol = _normalize_symbol(order.get("symbol") or _extract_nested_symbol(order))
        if target and order_symbol and order_symbol != target:
            continue
        order_type = _extract_order_type(order)
        trigger_price = _extract_trigger_price(order)
        if trigger_price is None:
            continue
        if "take" in order_type:
            take_profit_prices.append(trigger_price)
        elif "stop" in order_type and _extract_reduce_only(order):
            stop_prices.append(trigger_price)
    return (stop_prices[0] if stop_prices else None, take_profit_prices[0] if take_profit_prices else None)


def _extract_reduce_only(order: dict) -> bool:
    info = order.get("info") if isinstance(order.get("info"), dict) else {}
    params = order.get("params") if isinstance(order.get("params"), dict) else {}
    return bool(
        order.get("reduceOnly")
        or order.get("closePosition")
        or info.get("reduceOnly")
        or info.get("closePosition")
        or params.get("reduceOnly")
        or params.get("closePosition")
    )


def _extract_stop_price(orders: list[dict], symbol: str) -> float | None:
    stop_price, _ = _extract_protection_prices(orders, symbol)
    return stop_price


def _position_conflicts_with_record(record: AutoAddPositionRecord, live_position) -> bool:
    record_side = _normalize_side(record.side)
    live_side = _position_side(live_position)
    return bool(record_side and live_side and record_side != live_side)


def _next_active_trigger_price(tranches: list[AutoAddTrancheRecord]) -> float | None:
    candidates = [
        tranche.trigger_price
        for tranche in sorted(tranches, key=lambda item: item.tranche_index)
        if tranche.kind == AutoAddTrancheKind.ADD
        and tranche.status == AutoAddTrancheStatus.PLACED
        and tranche.trigger_price is not None
    ]
    return candidates[0] if candidates else None
