from typing import List, Protocol


class QuantScannerConfigRepository(Protocol):
    async def list_monitored_coins(self) -> List[str]:
        ...

    async def list_monitored_assets(self) -> List[str]:
        ...

    async def list_monitored_intervals(self) -> List[str]:
        ...
