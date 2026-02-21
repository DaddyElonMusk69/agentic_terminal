from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass(frozen=True)
class OiRankEntry:
    symbol: str
    rank: int
    delta: float
    delta_pct: Optional[float] = None
    current: Optional[float] = None
    previous: Optional[float] = None


@dataclass(frozen=True)
class OiRankCache:
    interval: str
    metric: str
    direction: str
    limit: int
    entries: List[OiRankEntry]
    status: str
    data_updated_at: Optional[datetime] = None
    refresh_started_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass(frozen=True)
class OiRankConfig:
    refresh_interval_minutes: int
    stale_ttl_minutes: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

