from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from app.application.automation import topics
from app.application.bus.outbox_service import OutboxService
from app.application.portfolio.service import PortfolioService
from app.application.position_origin.service import PositionOriginService
from app.application.trade_executor.service import TradeExecutorService
from app.domain.llm_response_worker.models import ExecutionAction, ExecutionIdea
from app.domain.position_origin.models import ActivePositionOriginRecord


class ProtectionReconcilerService:
    POLL_INTERVAL_SECONDS = 5
    EMPTY_SNAPSHOT_PRUNE_GRACE_SECONDS = 30

    def __init__(
        self,
        *,
        position_origin_service: PositionOriginService,
        portfolio_service: PortfolioService,
        trade_executor: TradeExecutorService,
        auto_add_service=None,
        outbox: OutboxService | None = None,
    ) -> None:
        self._position_origin_service = position_origin_service
        self._portfolio_service = portfolio_service
        self._trade_executor = trade_executor
        self._auto_add_service = auto_add_service
        self._outbox = outbox
        self._empty_snapshot_started_at: dict[str, datetime] = {}

    async def poll_once(self) -> int:
        account = await self._portfolio_service.get_active_account()
        if account is None:
            return 0

        try:
            snapshot = await self._portfolio_service.get_portfolio_snapshot()
        except Exception:
            return 0

        live_positions = [
            position
            for position in (snapshot.positions or [])
            if _position_is_open(position)
        ]
        live_symbols = sorted(
            {
                _normalize_symbol(getattr(position, "symbol", None))
                for position in live_positions
                if _normalize_symbol(getattr(position, "symbol", None))
            }
        )
        if live_symbols and self._auto_add_service is not None:
            try:
                await self._auto_add_service.cancel_missing_parent_positions(live_symbols)
            except Exception:
                pass
        if not live_symbols:
            if not await self._should_prune_empty_snapshot(account.id):
                return 0
            try:
                await self._position_origin_service.prune_missing(account.id, [])
            except Exception:
                pass
            return 0
        self._empty_snapshot_started_at.pop(account.id, None)
        try:
            await self._position_origin_service.prune_missing(account.id, live_symbols)
        except Exception:
            pass

        try:
            origin_rows = await self._position_origin_service.sync_live_positions(
                account.id,
                live_positions,
            )
        except Exception:
            try:
                origin_rows = await self._position_origin_service.get_many(account.id, live_symbols)
            except Exception:
                return 0

        managed: list[tuple[ActivePositionOriginRecord, Any]] = []
        for position in live_positions:
            symbol = _normalize_symbol(getattr(position, "symbol", None))
            if not symbol:
                continue
            origin = origin_rows.get(symbol)
            if origin is None:
                continue
            if origin.stop_loss_roe is None and origin.take_profit_roe is None:
                continue
            managed.append((origin, position))
        if not managed:
            return 0

        open_orders_index = await self._get_open_orders_index([origin.symbol for origin, _ in managed])
        handled = 0
        for origin, position in managed:
            if await self._reconcile_position(
                origin,
                position=position,
                open_orders=open_orders_index.get(origin.symbol, []),
            ):
                handled += 1
        return handled

    async def _reconcile_position(
        self,
        origin: ActivePositionOriginRecord,
        *,
        position: Any,
        open_orders: list[dict],
    ) -> bool:
        existing_stop, existing_take_profit = _extract_protection_prices(open_orders, origin.symbol)
        missing_stop = origin.stop_loss_roe is not None and existing_stop is None
        missing_take_profit = origin.take_profit_roe is not None and existing_take_profit is None
        if not missing_stop and not missing_take_profit:
            return False

        direction = _normalize_direction(getattr(position, "direction", None))
        entry_price = _safe_float(getattr(position, "entry_price", None))
        leverage = _safe_float(getattr(position, "leverage", None))
        if direction not in {"long", "short"} or entry_price is None or entry_price <= 0 or leverage is None or leverage <= 0:
            await self._emit(
                topics.POSITION_PROTECTION_RESTORE_FAILED,
                {
                    "symbol": origin.symbol,
                    "missing": _missing_labels(missing_stop, missing_take_profit),
                    "reason": "missing_live_position_context",
                },
            )
            return False

        restored: list[str] = []
        errors: list[str] = []

        if missing_stop and origin.stop_loss_roe is not None:
            stop_price = _calculate_stop_price_from_roe(
                risk_roe=origin.stop_loss_roe,
                entry_price=entry_price,
                leverage=leverage,
                direction=direction,
            )
            result = await self._trade_executor.execute(
                ExecutionIdea(
                    action=ExecutionAction.UPDATE_SL,
                    symbol=origin.symbol,
                    new_stop_loss=stop_price,
                    confidence=100.0,
                    reasoning="server protection reconciler restore stop loss",
                    execute=True,
                )
            )
            if result.success:
                restored.append("SL")
            else:
                errors.append(f"SL:{result.error or result.status}")

        if missing_take_profit and origin.take_profit_roe is not None:
            take_profit_price = _calculate_take_profit_price_from_roe(
                target_roe=origin.take_profit_roe,
                entry_price=entry_price,
                leverage=leverage,
                direction=direction,
            )
            result = await self._trade_executor.execute(
                ExecutionIdea(
                    action=ExecutionAction.UPDATE_TP,
                    symbol=origin.symbol,
                    new_take_profit=take_profit_price,
                    confidence=100.0,
                    reasoning="server protection reconciler restore take profit",
                    execute=True,
                )
            )
            if result.success:
                restored.append("TP")
            else:
                errors.append(f"TP:{result.error or result.status}")

        if restored:
            await self._emit(
                topics.POSITION_PROTECTION_RESTORED,
                {
                    "symbol": origin.symbol,
                    "restored": restored,
                    "missing": _missing_labels(missing_stop, missing_take_profit),
                },
            )
        if errors:
            await self._emit(
                topics.POSITION_PROTECTION_RESTORE_FAILED,
                {
                    "symbol": origin.symbol,
                    "missing": _missing_labels(missing_stop, missing_take_profit),
                    "restored": restored,
                    "reason": "; ".join(errors),
                },
            )
        return bool(restored)

    async def _get_open_orders_index(self, symbols: list[str]) -> dict[str, list[dict]]:
        unique = sorted({_normalize_symbol(symbol) for symbol in symbols if _normalize_symbol(symbol)})
        if not unique:
            return {}
        try:
            orders = await self._portfolio_service.get_open_orders(unique)
        except Exception:
            return {symbol: [] for symbol in unique}
        index: dict[str, list[dict]] = defaultdict(list)
        for order in orders or []:
            symbol = _normalize_symbol(order.get("symbol") or _extract_nested_symbol(order))
            if not symbol:
                continue
            index[symbol].append(order)
        return {symbol: index.get(symbol, []) for symbol in unique}

    async def _emit(self, topic: str, payload: dict[str, Any]) -> None:
        if self._outbox is None:
            return
        await self._outbox.enqueue_event(topic, payload)

    async def _should_prune_empty_snapshot(self, account_id: str) -> bool:
        now = datetime.now(timezone.utc)
        first_empty_seen_at = self._empty_snapshot_started_at.get(account_id)
        if first_empty_seen_at is None:
            self._empty_snapshot_started_at[account_id] = now
            return False
        return now - first_empty_seen_at >= timedelta(seconds=self.EMPTY_SNAPSHOT_PRUNE_GRACE_SECONDS)


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


def _safe_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _position_is_open(position: Any) -> bool:
    size = _safe_float(getattr(position, "size", None))
    if size is None:
        return True
    return abs(size) > 1e-8


def _extract_nested_symbol(order: dict) -> str | None:
    info = order.get("info") if isinstance(order.get("info"), dict) else {}
    value = order.get("symbol") or info.get("symbol")
    if isinstance(value, str) and value.strip():
        return value
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
        elif "stop" in order_type:
            stop_prices.append(trigger_price)
    return (stop_prices[0] if stop_prices else None, take_profit_prices[0] if take_profit_prices else None)


def _calculate_stop_price_from_roe(
    *,
    risk_roe: float,
    entry_price: float,
    leverage: float,
    direction: str,
) -> float:
    normalized_roe = abs(float(risk_roe))
    if direction == "long":
        return entry_price * (1.0 - (normalized_roe / leverage))
    return entry_price * (1.0 + (normalized_roe / leverage))


def _calculate_take_profit_price_from_roe(
    *,
    target_roe: float,
    entry_price: float,
    leverage: float,
    direction: str,
) -> float:
    normalized_roe = abs(float(target_roe))
    if direction == "long":
        return entry_price * (1.0 + (normalized_roe / leverage))
    return entry_price * (1.0 - (normalized_roe / leverage))


def _missing_labels(missing_stop: bool, missing_take_profit: bool) -> list[str]:
    labels: list[str] = []
    if missing_stop:
        labels.append("SL")
    if missing_take_profit:
        labels.append("TP")
    return labels
