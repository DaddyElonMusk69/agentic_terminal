from __future__ import annotations

from typing import List, Optional, Protocol

from app.domain.pending_entry.models import PendingEntryRecord, PendingEntrySnapshot


class PendingEntryRepository(Protocol):
    async def create(self, record: PendingEntryRecord) -> PendingEntryRecord:
        ...

    async def update(self, record: PendingEntryRecord) -> PendingEntryRecord:
        ...

    async def get(self, entry_id: str) -> Optional[PendingEntryRecord]:
        ...

    async def get_by_exchange_order_id(
        self,
        account_id: str,
        exchange_order_id: str,
    ) -> Optional[PendingEntryRecord]:
        ...

    async def list_active(self, account_id: str) -> List[PendingEntryRecord]:
        ...

    async def list_active_for_symbol(
        self,
        account_id: str,
        symbol: str,
    ) -> List[PendingEntryRecord]:
        ...

    async def list_active_snapshots(self, account_id: str) -> List[PendingEntrySnapshot]:
        ...
