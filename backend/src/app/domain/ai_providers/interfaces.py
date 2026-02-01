from typing import List, Protocol

from app.domain.ai_providers.models import ProviderConfig


class ProviderConfigRepository(Protocol):
    async def list_configs(self) -> List[ProviderConfig]:
        ...

    async def get_config(self, provider: str) -> ProviderConfig | None:
        ...

    async def upsert(self, config: ProviderConfig) -> ProviderConfig:
        ...

    async def delete(self, provider: str) -> None:
        ...
