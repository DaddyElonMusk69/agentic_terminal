from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class ActivePositionOriginRecord:
    account_id: str
    symbol: str
    anchor_frame: Optional[str] = None
    active_tunnel: Optional[str] = None
    stop_loss_roe: Optional[float] = None
    take_profit_roe: Optional[float] = None
    position_side: Optional[str] = None
    exchange_opened_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    peak_roe: Optional[float] = None
    peak_roe_updated_at: Optional[datetime] = None
    peak_roe_basis_entry_price: Optional[float] = None
    peak_roe_basis_size: Optional[float] = None
    peak_roe_basis_leverage: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
