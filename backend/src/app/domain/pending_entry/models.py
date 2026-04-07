from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class PendingEntryStatus(Enum):
    RESTING = "RESTING"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    PROTECTION_PENDING = "PROTECTION_PENDING"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    ORPHANED = "ORPHANED"


ACTIVE_PENDING_ENTRY_STATUSES = {
    PendingEntryStatus.RESTING,
    PendingEntryStatus.PROTECTION_PENDING,
}


TERMINAL_PENDING_ENTRY_STATUSES = {
    PendingEntryStatus.PARTIALLY_FILLED,
    PendingEntryStatus.FILLED,
    PendingEntryStatus.CANCELED,
    PendingEntryStatus.EXPIRED,
    PendingEntryStatus.FAILED,
    PendingEntryStatus.ORPHANED,
}


@dataclass(frozen=True)
class PendingEntryRecord:
    id: str
    account_id: str
    session_id: Optional[str]
    symbol: str
    exchange_symbol: str
    side: str
    exchange_order_id: str
    limit_price: float
    intended_size_usd: Optional[float]
    intended_quantity: Optional[float]
    filled_quantity: Optional[float]
    leverage: Optional[int]
    time_in_force: Optional[str]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    stop_loss_roe: Optional[float]
    take_profit_roe: Optional[float]
    anchor_frame: Optional[str]
    active_tunnel: Optional[str]
    status: PendingEntryStatus
    placed_at: datetime
    expires_at: datetime
    resolved_at: Optional[datetime] = None
    last_reconciled_at: Optional[datetime] = None
    last_error: Optional[str] = None
    order_payload: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass(frozen=True)
class PendingEntrySnapshot:
    id: str
    symbol: str
    side: str
    limit_price: float
    status: PendingEntryStatus
    placed_at: datetime
    expires_at: datetime
    exchange_order_id: str
    filled_quantity: Optional[float] = None
    intended_quantity: Optional[float] = None
    current_mark: Optional[float] = None

    @property
    def filled_pct(self) -> float:
        if self.intended_quantity is None or self.intended_quantity <= 0:
            return 0.0
        filled = self.filled_quantity or 0.0
        if filled <= 0:
            return 0.0
        return max(0.0, min(100.0, (filled / self.intended_quantity) * 100.0))
