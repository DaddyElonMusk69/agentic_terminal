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
    ) -> ActivePositionOriginRecord | None:
        normalized_account_id = str(account_id or "").strip()
        normalized_symbol = normalize_position_origin_symbol(symbol)
        if not normalized_account_id or not normalized_symbol:
            return None

        existing = await self.get_one(normalized_account_id, normalized_symbol)

        normalized_anchor = (
            existing.anchor_frame if anchor_frame is _UNSET else _normalize_anchor_frame(anchor_frame)
        )
        normalized_tunnel = (
            existing.active_tunnel if active_tunnel is _UNSET else _normalize_active_tunnel(active_tunnel)
        )
        normalized_stop_loss_roe = (
            existing.stop_loss_roe if stop_loss_roe is _UNSET else _normalize_optional_float(stop_loss_roe)
        )
        normalized_take_profit_roe = (
            existing.take_profit_roe
            if take_profit_roe is _UNSET
            else _normalize_optional_float(take_profit_roe)
        )

        if (
            normalized_anchor is None
            and normalized_tunnel is None
            and normalized_stop_loss_roe is None
            and normalized_take_profit_roe is None
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
        )

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
