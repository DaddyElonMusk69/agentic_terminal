from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class AutoAddStatus(Enum):
    WAITING_PROTECTION = "WAITING_PROTECTION"
    ACTIVE = "ACTIVE"
    ADDING = "ADDING"
    WAITING_CAPACITY = "WAITING_CAPACITY"
    PROTECTION_PENDING = "PROTECTION_PENDING"
    COMPLETED = "COMPLETED"
    CLOSED = "CLOSED"
    DETACHED = "DETACHED"
    ERROR = "ERROR"


ACTIVE_AUTO_ADD_STATUSES = {
    AutoAddStatus.WAITING_PROTECTION,
    AutoAddStatus.ACTIVE,
    AutoAddStatus.ADDING,
    AutoAddStatus.WAITING_CAPACITY,
    AutoAddStatus.PROTECTION_PENDING,
}


class AutoAddTrancheKind(Enum):
    INITIAL = "INITIAL"
    ADD = "ADD"


class AutoAddTrancheStatus(Enum):
    INITIAL = "INITIAL"
    PLACED = "PLACED"
    RESOLVED = "RESOLVED"
    CANCELED = "CANCELED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class AutoAddPositionRecord:
    id: str
    account_id: str
    session_id: Optional[str]
    symbol: str
    side: str
    status: AutoAddStatus
    initial_margin_used: Optional[float]
    initial_stop_price: Optional[float]
    original_risk_usd: Optional[float]
    trigger_basis_price: Optional[float]
    next_trigger_price: Optional[float]
    initial_entry_price: Optional[float]
    initial_quantity: Optional[float]
    expected_quantity: Optional[float]
    leverage: Optional[float]
    add_count: int
    max_tranches: int
    trigger_atr_multiple: float
    tranche_margin_pct: float
    protected_stop_roe: float
    last_atr_value: Optional[float] = None
    last_error: Optional[str] = None
    last_capacity_blocked_at: Optional[datetime] = None
    last_trade_guard_reason: Optional[str] = None
    last_seen_position_size: Optional[float] = None
    last_seen_entry_price: Optional[float] = None
    last_seen_mark_price: Optional[float] = None
    last_seen_margin: Optional[float] = None
    active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None


@dataclass(frozen=True)
class AutoAddTrancheRecord:
    id: str
    auto_add_position_id: str
    tranche_index: int
    kind: AutoAddTrancheKind
    status: AutoAddTrancheStatus
    exchange_order_id: Optional[str]
    trigger_price: Optional[float]
    fill_price: Optional[float]
    filled_quantity: Optional[float]
    margin_used: Optional[float]
    position_notional_usd: Optional[float]
    fill_time: Optional[datetime]
    atr_value: Optional[float]
    trigger_basis_price: Optional[float]
    last_error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass(frozen=True)
class AutoAddPositionSnapshot:
    record: AutoAddPositionRecord
    tranches: tuple[AutoAddTrancheRecord, ...] = field(default_factory=tuple)
