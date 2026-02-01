from datetime import date
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.application.risk_management.dependencies import (
    get_risk_management_config_service,
    get_risk_management_service,
)
from app.common.api import ApiMeta


router = APIRouter(prefix="/risk-management", tags=["risk-management"])


class RiskManagementConfigPayload(BaseModel):
    final_goal_usd: float = Field(..., ge=0)
    exposure_pct: float = Field(..., ge=1, le=100)
    goal_deadline: Optional[date] = None


class RiskManagementConfigView(BaseModel):
    final_goal_usd: float
    exposure_pct: float
    goal_deadline: Optional[date] = None


class RiskManagementConfigResponse(BaseModel):
    data: RiskManagementConfigView
    meta: Optional[ApiMeta] = None


class RiskManagementSummaryView(BaseModel):
    config: RiskManagementConfigView
    account_value: Optional[float] = None
    goal_cny: float
    fx_rate_cny: float
    exposure_usd: Optional[float] = None
    progress_pct: Optional[float] = None
    progress_gap_usd: Optional[float] = None
    days_left: Optional[int] = None
    daily_target_pct: Optional[float] = None
    daily_target_usd: Optional[float] = None


class RiskManagementSummaryResponse(BaseModel):
    data: RiskManagementSummaryView
    meta: Optional[ApiMeta] = None


def _meta(request: Request) -> ApiMeta:
    return ApiMeta(request_id=getattr(request.state, "request_id", None))


@router.get("/config", response_model=RiskManagementConfigResponse)
async def get_risk_config(request: Request) -> RiskManagementConfigResponse:
    service = get_risk_management_config_service()
    config = await service.get_config()
    view = RiskManagementConfigView(
        final_goal_usd=config.final_goal_usd,
        exposure_pct=config.exposure_pct,
        goal_deadline=config.goal_deadline,
    )
    return RiskManagementConfigResponse(data=view, meta=_meta(request))


@router.put("/config", response_model=RiskManagementConfigResponse)
async def update_risk_config(
    payload: RiskManagementConfigPayload,
    request: Request,
) -> RiskManagementConfigResponse:
    service = get_risk_management_config_service()
    config = await service.update_config(
        final_goal_usd=payload.final_goal_usd,
        exposure_pct=payload.exposure_pct,
        goal_deadline=payload.goal_deadline,
    )
    view = RiskManagementConfigView(
        final_goal_usd=config.final_goal_usd,
        exposure_pct=config.exposure_pct,
        goal_deadline=config.goal_deadline,
    )
    return RiskManagementConfigResponse(data=view, meta=_meta(request))


@router.get("/summary", response_model=RiskManagementSummaryResponse)
async def get_risk_summary(request: Request) -> RiskManagementSummaryResponse:
    service = get_risk_management_service()
    summary = await service.get_summary()
    config_payload = summary.get("config") or {}
    view = RiskManagementSummaryView(
        config=RiskManagementConfigView(
            final_goal_usd=config_payload.get("final_goal_usd", 0.0),
            exposure_pct=config_payload.get("exposure_pct", 20.0),
            goal_deadline=config_payload.get("goal_deadline"),
        ),
        account_value=summary.get("account_value"),
        goal_cny=summary.get("goal_cny", 0.0),
        fx_rate_cny=summary.get("fx_rate_cny", 7.2),
        exposure_usd=summary.get("exposure_usd"),
        progress_pct=summary.get("progress_pct"),
        progress_gap_usd=summary.get("progress_gap_usd"),
        days_left=summary.get("days_left"),
        daily_target_pct=summary.get("daily_target_pct"),
        daily_target_usd=summary.get("daily_target_usd"),
    )
    return RiskManagementSummaryResponse(data=view, meta=_meta(request))
