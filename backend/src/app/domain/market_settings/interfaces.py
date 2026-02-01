from typing import List, Protocol


class MarketSettingsRepository(Protocol):
    async def list_assets(self) -> List[str]:
        ...

    async def list_intervals(self) -> List[str]:
        ...

    async def add_asset(self, symbol: str) -> None:
        ...

    async def remove_asset(self, symbol: str) -> None:
        ...

    async def add_interval(self, interval: str) -> None:
        ...

    async def remove_interval(self, interval: str) -> None:
        ...
