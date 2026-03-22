from typing import List, Protocol

from app.domain.position_origin.models import ActivePositionOriginRecord


class ActivePositionOriginRepository(Protocol):
    async def upsert(
        self,
        account_id: str,
        symbol: str,
        anchor_frame: str | None,
        active_tunnel: str | None,
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
