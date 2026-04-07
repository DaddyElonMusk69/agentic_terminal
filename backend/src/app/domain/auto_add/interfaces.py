from __future__ import annotations

from typing import Protocol

from app.domain.auto_add.models import (
    AutoAddPositionRecord,
    AutoAddPositionSnapshot,
    AutoAddTrancheRecord,
)


class AutoAddRepository(Protocol):
    async def create_position(self, record: AutoAddPositionRecord) -> AutoAddPositionRecord:
        ...

    async def update_position(self, record: AutoAddPositionRecord) -> AutoAddPositionRecord:
        ...

    async def get_position(self, position_id: str) -> AutoAddPositionRecord | None:
        ...

    async def get_active_position_for_symbol(
        self,
        account_id: str,
        symbol: str,
    ) -> AutoAddPositionRecord | None:
        ...

    async def get_latest_position_for_symbol(
        self,
        account_id: str,
        symbol: str,
    ) -> AutoAddPositionRecord | None:
        ...

    async def list_active_positions(self, account_id: str) -> list[AutoAddPositionRecord]:
        ...

    async def list_latest_positions_for_symbols(
        self,
        account_id: str,
        symbols: list[str],
    ) -> list[AutoAddPositionRecord]:
        ...

    async def create_tranche(self, record: AutoAddTrancheRecord) -> AutoAddTrancheRecord:
        ...

    async def update_tranche(self, record: AutoAddTrancheRecord) -> AutoAddTrancheRecord:
        ...

    async def list_tranches(self, auto_add_position_id: str) -> list[AutoAddTrancheRecord]:
        ...

    async def get_snapshot(self, auto_add_position_id: str) -> AutoAddPositionSnapshot | None:
        ...
