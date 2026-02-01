from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional


@dataclass(frozen=True)
class RiskManagementConfig:
    final_goal_usd: float
    exposure_pct: float
    goal_deadline: Optional[date]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


DEFAULT_RISK_MANAGEMENT_CONFIG = RiskManagementConfig(
    final_goal_usd=0.0,
    exposure_pct=20.0,
    goal_deadline=None,
)
