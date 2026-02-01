from typing import Optional, Protocol

from app.domain.automation.models import AutomationConfig


class AutomationConfigRepository(Protocol):
    async def get_config(self) -> Optional[AutomationConfig]:
        ...

    async def upsert(self, config: AutomationConfig) -> AutomationConfig:
        ...
