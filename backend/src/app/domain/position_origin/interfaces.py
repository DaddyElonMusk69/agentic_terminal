from datetime import datetime
from typing import List, Protocol

from app.domain.position_origin.models import ActivePositionOriginRecord


class ActivePositionOriginRepository(Protocol):
    async def upsert(
        self,
        account_id: str,
        symbol: str,
        anchor_frame: str | None,
        active_tunnel: str | None,
        stop_loss_roe: float | None,
        take_profit_roe: float | None,
        position_side: str | None,
        exchange_opened_at: datetime | None,
        last_seen_at: datetime | None,
        peak_roe: float | None,
        peak_roe_updated_at: datetime | None,
        peak_roe_basis_entry_price: float | None,
        peak_roe_basis_size: float | None,
        peak_roe_basis_leverage: float | None,
    ) -> ActivePositionOriginRecord:
        ...

    async def get_many(
        self,
        account_id: str,
        symbols: list[str],
    ) -> List[ActivePositionOriginRecord]:
        ...

    async def delete(
        self,
        account_id: str,
        symbol: str,
    ) -> bool:
        ...

    async def prune_missing(
        self,
        account_id: str,
        live_symbols: list[str],
    ) -> int:
        ...
