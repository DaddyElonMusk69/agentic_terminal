from typing import Optional, Protocol

from app.domain.dynamic_assets.models import DynamicAssetsConfig


class DynamicAssetsConfigRepository(Protocol):
    async def get_config(self) -> Optional[DynamicAssetsConfig]:
        ...

    async def upsert(self, config: DynamicAssetsConfig) -> DynamicAssetsConfig:
        ...
