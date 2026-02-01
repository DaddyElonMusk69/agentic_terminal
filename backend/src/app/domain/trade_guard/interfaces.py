from typing import Optional, Protocol

from app.domain.trade_guard.models import TradeGuardConfig


class TradeGuardConfigRepository(Protocol):
    async def get_config(self) -> Optional[TradeGuardConfig]:
        ...

    async def upsert(self, config: TradeGuardConfig) -> TradeGuardConfig:
        ...
