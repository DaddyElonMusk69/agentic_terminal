from typing import Protocol, List

from app.domain.ema_scanner.models import EmaScannerLine


class EmaScannerConfigRepository(Protocol):
    async def get_tolerance(self) -> float | None:
        ...

    async def set_tolerance(self, value: float) -> float:
        ...

    async def get_scan_intervals(self) -> List[str] | None:
        ...

    async def set_scan_intervals(self, intervals: List[str] | None) -> List[str] | None:
        ...

    async def list_ema_lines(self) -> List[int]:
        ...

    async def list_ema_line_records(self) -> List[EmaScannerLine]:
        ...

    async def add_ema_line(self, length: int) -> List[EmaScannerLine]:
        ...

    async def remove_ema_line(self, line_id: int) -> List[EmaScannerLine]:
        ...

    async def list_monitored_coins(self) -> List[str]:
        ...

    async def list_monitored_assets(self) -> List[str]:
        ...

    async def list_monitored_intervals(self) -> List[str]:
        ...
