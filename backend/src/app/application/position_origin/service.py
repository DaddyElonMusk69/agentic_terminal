from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Sequence

from app.domain.position_origin.interfaces import ActivePositionOriginRepository
from app.domain.position_origin.models import ActivePositionOriginRecord
from app.domain.position_origin.symbols import normalize_position_origin_symbol

_UNSET = object()


class PositionOriginService:
    def __init__(self, repository: ActivePositionOriginRepository) -> None:
        self._repository = repository

    async def upsert(
        self,
        account_id: str,
        symbol: Any,
        anchor_frame: Any = _UNSET,
        active_tunnel: Any = _UNSET,
        *,
        stop_loss_roe: Any = _UNSET,
        take_profit_roe: Any = _UNSET,
        position_side: Any = _UNSET,
        exchange_opened_at: Any = _UNSET,
        last_seen_at: Any = _UNSET,
        peak_roe: Any = _UNSET,
        peak_roe_updated_at: Any = _UNSET,
        peak_roe_basis_entry_price: Any = _UNSET,
        peak_roe_basis_size: Any = _UNSET,
        peak_roe_basis_leverage: Any = _UNSET,
    ) -> ActivePositionOriginRecord | None:
        normalized_account_id = str(account_id or "").strip()
        normalized_symbol = normalize_position_origin_symbol(symbol)
        if not normalized_account_id or not normalized_symbol:
            return None

        existing = await self.get_one(normalized_account_id, normalized_symbol)

        normalized_anchor = (
            existing.anchor_frame
            if anchor_frame is _UNSET and existing is not None
            else _normalize_anchor_frame(None if anchor_frame is _UNSET else anchor_frame)
        )
        normalized_tunnel = (
            existing.active_tunnel
            if active_tunnel is _UNSET and existing is not None
            else _normalize_active_tunnel(None if active_tunnel is _UNSET else active_tunnel)
        )
        normalized_stop_loss_roe = (
            existing.stop_loss_roe
            if stop_loss_roe is _UNSET and existing is not None
            else _normalize_optional_float(None if stop_loss_roe is _UNSET else stop_loss_roe)
        )
        normalized_take_profit_roe = (
            existing.take_profit_roe
            if take_profit_roe is _UNSET and existing is not None
            else _normalize_optional_float(None if take_profit_roe is _UNSET else take_profit_roe)
        )
        normalized_position_side = (
            existing.position_side
            if position_side is _UNSET and existing is not None
            else _normalize_position_side(None if position_side is _UNSET else position_side)
        )
        normalized_exchange_opened_at = (
            existing.exchange_opened_at
            if exchange_opened_at is _UNSET and existing is not None
            else _normalize_optional_datetime(
                None if exchange_opened_at is _UNSET else exchange_opened_at
            )
        )
        normalized_last_seen_at = (
            existing.last_seen_at
            if last_seen_at is _UNSET and existing is not None
            else _normalize_optional_datetime(None if last_seen_at is _UNSET else last_seen_at)
        )
        normalized_peak_roe = (
            existing.peak_roe
            if peak_roe is _UNSET and existing is not None
            else _normalize_optional_float(None if peak_roe is _UNSET else peak_roe)
        )
        normalized_peak_roe_updated_at = (
            existing.peak_roe_updated_at
            if peak_roe_updated_at is _UNSET and existing is not None
            else _normalize_optional_datetime(
                None if peak_roe_updated_at is _UNSET else peak_roe_updated_at
            )
        )
        normalized_peak_roe_basis_entry_price = (
            existing.peak_roe_basis_entry_price
            if peak_roe_basis_entry_price is _UNSET and existing is not None
            else _normalize_optional_float(
                None if peak_roe_basis_entry_price is _UNSET else peak_roe_basis_entry_price
            )
        )
        normalized_peak_roe_basis_size = (
            existing.peak_roe_basis_size
            if peak_roe_basis_size is _UNSET and existing is not None
            else _normalize_optional_float(
                None if peak_roe_basis_size is _UNSET else peak_roe_basis_size
            )
        )
        normalized_peak_roe_basis_leverage = (
            existing.peak_roe_basis_leverage
            if peak_roe_basis_leverage is _UNSET and existing is not None
            else _normalize_optional_float(
                None if peak_roe_basis_leverage is _UNSET else peak_roe_basis_leverage
            )
        )

        if (
            normalized_anchor is None
            and normalized_tunnel is None
            and normalized_stop_loss_roe is None
            and normalized_take_profit_roe is None
            and normalized_position_side is None
            and normalized_exchange_opened_at is None
            and normalized_last_seen_at is None
            and normalized_peak_roe is None
            and normalized_peak_roe_updated_at is None
            and normalized_peak_roe_basis_entry_price is None
            and normalized_peak_roe_basis_size is None
            and normalized_peak_roe_basis_leverage is None
        ):
            await self._repository.delete(normalized_account_id, normalized_symbol)
            return None

        return await self._repository.upsert(
            account_id=normalized_account_id,
            symbol=normalized_symbol,
            anchor_frame=normalized_anchor,
            active_tunnel=normalized_tunnel,
            stop_loss_roe=normalized_stop_loss_roe,
            take_profit_roe=normalized_take_profit_roe,
            position_side=normalized_position_side,
            exchange_opened_at=normalized_exchange_opened_at,
            last_seen_at=normalized_last_seen_at,
            peak_roe=normalized_peak_roe,
            peak_roe_updated_at=normalized_peak_roe_updated_at,
            peak_roe_basis_entry_price=normalized_peak_roe_basis_entry_price,
            peak_roe_basis_size=normalized_peak_roe_basis_size,
            peak_roe_basis_leverage=normalized_peak_roe_basis_leverage,
        )

    async def sync_live_positions(
        self,
        account_id: str,
        positions: Sequence[Any],
    ) -> Dict[str, ActivePositionOriginRecord]:
        normalized_account_id = str(account_id or "").strip()
        live_positions = list(positions or [])
        if not normalized_account_id or not live_positions:
            return {}

        live_symbols = _normalize_symbols(
            [getattr(position, "symbol", None) for position in live_positions]
        )
        existing_rows = await self.get_many(normalized_account_id, live_symbols)
        updated_rows: Dict[str, ActivePositionOriginRecord] = dict(existing_rows)

        for position in live_positions:
            normalized_symbol = normalize_position_origin_symbol(getattr(position, "symbol", None))
            if not normalized_symbol:
                continue

            existing = updated_rows.get(normalized_symbol)
            side = _resolve_live_position_side(position)
            exchange_opened_at = _normalize_optional_datetime(getattr(position, "opened_at", None))
            entry_price = _normalize_optional_float(getattr(position, "entry_price", None))
            basis_size = _normalize_position_size(getattr(position, "size", None))
            leverage = _normalize_optional_float(getattr(position, "leverage", None))
            current_roe = _compute_position_roe(position)
            now = datetime.now(timezone.utc)

            basis_changed = _has_peak_basis_changed(
                existing,
                side=side,
                exchange_opened_at=exchange_opened_at,
                entry_price=entry_price,
                size=basis_size,
                leverage=leverage,
            )

            next_peak_roe = existing.peak_roe if existing is not None else None
            next_peak_roe_updated_at = existing.peak_roe_updated_at if existing is not None else None
            next_basis_entry_price = (
                existing.peak_roe_basis_entry_price if existing is not None else None
            )
            next_basis_size = existing.peak_roe_basis_size if existing is not None else None
            next_basis_leverage = existing.peak_roe_basis_leverage if existing is not None else None

            if basis_changed:
                next_peak_roe = current_roe
                next_peak_roe_updated_at = now if current_roe is not None else None
                next_basis_entry_price = entry_price
                next_basis_size = basis_size
                next_basis_leverage = leverage
            elif current_roe is not None and (next_peak_roe is None or current_roe > next_peak_roe):
                next_peak_roe = current_roe
                next_peak_roe_updated_at = now
                if next_basis_entry_price is None:
                    next_basis_entry_price = entry_price
                if next_basis_size is None:
                    next_basis_size = basis_size
                if next_basis_leverage is None:
                    next_basis_leverage = leverage

            record = await self.upsert(
                account_id=normalized_account_id,
                symbol=normalized_symbol,
                position_side=side,
                exchange_opened_at=exchange_opened_at,
                last_seen_at=now,
                peak_roe=next_peak_roe,
                peak_roe_updated_at=next_peak_roe_updated_at,
                peak_roe_basis_entry_price=next_basis_entry_price,
                peak_roe_basis_size=next_basis_size,
                peak_roe_basis_leverage=next_basis_leverage,
            )
            if record is None:
                updated_rows.pop(normalized_symbol, None)
                continue
            updated_rows[normalized_symbol] = record

        return updated_rows

    async def get_one(
        self,
        account_id: str,
        symbol: Any,
    ) -> ActivePositionOriginRecord | None:
        normalized_account_id = str(account_id or "").strip()
        normalized_symbol = normalize_position_origin_symbol(symbol)
        if not normalized_account_id or not normalized_symbol:
            return None
        rows = await self._repository.get_many(normalized_account_id, [normalized_symbol])
        if not rows:
            return None
        return rows[0]

    async def get_many(
        self,
        account_id: str,
        symbols: Sequence[Any],
    ) -> Dict[str, ActivePositionOriginRecord]:
        normalized_account_id = str(account_id or "").strip()
        normalized_symbols = _normalize_symbols(symbols)
        if not normalized_account_id or not normalized_symbols:
            return {}
        rows = await self._repository.get_many(normalized_account_id, normalized_symbols)
        return {row.symbol: row for row in rows}

    async def delete(
        self,
        account_id: str,
        symbol: Any,
    ) -> bool:
        normalized_account_id = str(account_id or "").strip()
        normalized_symbol = normalize_position_origin_symbol(symbol)
        if not normalized_account_id or not normalized_symbol:
            return False
        return await self._repository.delete(normalized_account_id, normalized_symbol)

    async def prune_missing(
        self,
        account_id: str,
        live_symbols: Sequence[Any],
    ) -> int:
        normalized_account_id = str(account_id or "").strip()
        if not normalized_account_id:
            return 0
        return await self._repository.prune_missing(
            normalized_account_id,
            _normalize_symbols(live_symbols),
        )


def _normalize_symbols(symbols: Sequence[Any]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        value = normalize_position_origin_symbol(symbol)
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _normalize_anchor_frame(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_active_tunnel(value: Any) -> str | None:
    if isinstance(value, list):
        for item in value:
            candidate = str(item).strip()
            if candidate:
                return candidate
        return None
    if value is None:
        return None
    candidate = str(value).strip()
    return candidate or None


def _normalize_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return None
    return normalized


def _normalize_optional_datetime(value: Any) -> datetime | None:
    if value is None or not hasattr(value, "isoformat"):
        return None
    return value


def _normalize_position_side(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"long", "short"}:
        return normalized
    return None


def _resolve_live_position_side(position: Any) -> str | None:
    direction = _normalize_position_side(getattr(position, "direction", None))
    if direction is not None:
        return direction
    size = _normalize_optional_float(getattr(position, "size", None))
    if size is None:
        return None
    if size > 0:
        return "long"
    if size < 0:
        return "short"
    return None


def _normalize_position_size(value: Any) -> float | None:
    normalized = _normalize_optional_float(value)
    if normalized is None:
        return None
    return abs(normalized)


def _compute_position_roe(position: Any) -> float | None:
    margin = _normalize_optional_float(getattr(position, "margin", None))
    if margin is None or margin <= 0:
        entry_price = _normalize_optional_float(getattr(position, "entry_price", None))
        leverage = _normalize_optional_float(getattr(position, "leverage", None))
        size = _normalize_optional_float(getattr(position, "size", None))
        if (
            entry_price is None
            or entry_price <= 0
            or leverage is None
            or leverage <= 0
            or size is None
            or size == 0
        ):
            return None
        margin = abs(size * entry_price) / leverage
    unrealized_pnl = _normalize_optional_float(getattr(position, "unrealized_pnl", None))
    if unrealized_pnl is None or margin <= 0:
        return None
    return (unrealized_pnl / margin) * 100.0


def _has_peak_basis_changed(
    existing: ActivePositionOriginRecord | None,
    *,
    side: str | None,
    exchange_opened_at: datetime | None,
    entry_price: float | None,
    size: float | None,
    leverage: float | None,
) -> bool:
    if existing is None:
        return True
    if existing.position_side is not None and side is not None and existing.position_side != side:
        return True
    if _datetimes_differ(existing.exchange_opened_at, exchange_opened_at):
        return True
    if _floats_differ(existing.peak_roe_basis_entry_price, entry_price):
        return True
    if _floats_differ(existing.peak_roe_basis_size, size):
        return True
    if _floats_differ(existing.peak_roe_basis_leverage, leverage):
        return True
    return False


def _datetimes_differ(left: datetime | None, right: datetime | None) -> bool:
    if left is None or right is None:
        return False
    return abs((left - right).total_seconds()) > 1.0


def _floats_differ(left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return False
    tolerance = max(1e-9, abs(left) * 1e-6, abs(right) * 1e-6)
    return abs(left - right) > tolerance
