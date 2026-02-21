from __future__ import annotations

from typing import Protocol, Optional, List

from app.domain.oi_rank.models import OiRankCache, OiRankConfig


class OiRankCacheRepository(Protocol):
    async def get_cache(self, interval: str, metric: str, direction: str) -> Optional[OiRankCache]:
        ...

    async def list_by_interval(self, interval: str) -> List[OiRankCache]:
        ...

    async def upsert(self, cache: OiRankCache) -> OiRankCache:
        ...


class OiRankConfigRepository(Protocol):
    async def get_config(self) -> Optional[OiRankConfig]:
        ...

    async def upsert(self, config: OiRankConfig) -> OiRankConfig:
        ...

