from typing import Optional, Protocol

from app.domain.ema_state_manager.models import EmaStateManagerConfig


class EmaStateManagerConfigRepository(Protocol):
    async def get_config(self) -> Optional[EmaStateManagerConfig]:
        ...

    async def upsert(self, config: EmaStateManagerConfig) -> EmaStateManagerConfig:
        ...
