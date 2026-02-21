from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional


@dataclass(frozen=True)
class DynamicAssetsConfig:
    enabled: bool
    api_key: Optional[str]
    oi_source: str
    sources: Dict[str, object]
    refresh_interval_seconds: int
    volatility_threshold_pct: float = 20.0
    last_success_assets: Optional[List[str]] = None
    last_success_at: Optional[datetime] = None
    last_fetch_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass(frozen=True)
class DynamicAssetsState:
    assets: List[str]
    enabled: bool
    binance_active: bool
    is_stale: bool
    last_success_at: Optional[datetime] = None
    last_fetch_at: Optional[datetime] = None
