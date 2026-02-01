from __future__ import annotations

from datetime import date
from typing import Optional

from app.application.portfolio.dependencies import get_portfolio_service
from app.application.risk_management.config_service import RiskManagementConfigService

_CNY_FX_RATE = 7.2


class RiskManagementService:
    def __init__(
        self,
        config_service: RiskManagementConfigService,
        portfolio_service=None,
    ) -> None:
        self._config_service = config_service
        self._portfolio_service = portfolio_service or get_portfolio_service()

    async def get_summary(self) -> dict:
        config = await self._config_service.get_config()
        account_value = await self._resolve_account_value()

        goal_usd = float(config.final_goal_usd)
        exposure_pct = float(config.exposure_pct)
        goal_deadline = config.goal_deadline

        exposure_usd = None
        if account_value is not None:
            exposure_usd = account_value * (exposure_pct / 100.0)

        progress_pct = None
        progress_gap_usd = None
        if account_value is not None and goal_usd > 0:
            progress_pct = (account_value / goal_usd) * 100.0
            progress_gap_usd = max(goal_usd - account_value, 0.0)

        days_left = _days_left(goal_deadline)

        daily_target_pct = None
        daily_target_usd = None
        if account_value is not None and goal_usd > 0 and days_left and days_left > 0:
            if goal_usd <= account_value:
                daily_target_pct = 0.0
                daily_target_usd = 0.0
            else:
                rate = (goal_usd / account_value) ** (1 / days_left) - 1
                daily_target_pct = rate * 100.0
                daily_target_usd = account_value * rate

        return {
            "config": {
                "final_goal_usd": goal_usd,
                "exposure_pct": exposure_pct,
                "goal_deadline": goal_deadline.isoformat() if goal_deadline else None,
            },
            "account_value": account_value,
            "goal_cny": goal_usd * _CNY_FX_RATE,
            "fx_rate_cny": _CNY_FX_RATE,
            "exposure_usd": exposure_usd,
            "progress_pct": progress_pct,
            "progress_gap_usd": progress_gap_usd,
            "days_left": days_left,
            "daily_target_pct": daily_target_pct,
            "daily_target_usd": daily_target_usd,
        }

    async def _resolve_account_value(self) -> Optional[float]:
        try:
            snapshot = await self._portfolio_service.get_portfolio_snapshot()
        except Exception:
            return None
        return float(snapshot.state.account_value)


def _days_left(goal_deadline: Optional[date]) -> Optional[int]:
    if not goal_deadline:
        return None
    today = date.today()
    delta = (goal_deadline - today).days
    return max(delta, 0)
