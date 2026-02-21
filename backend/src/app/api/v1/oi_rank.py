from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.application.oi_rank.dependencies import get_oi_rank_service
from app.common.api import ApiMeta
from app.domain.oi_rank.models import OiRankEntry


router = APIRouter(prefix="/oi-rank", tags=["oi-rank"])


class OiRankPosition(BaseModel):
    symbol: str
    rank: int
    delta: float
    delta_pct: Optional[float] = None
    current: Optional[float] = None
    previous: Optional[float] = None


class OiRankData(BaseModel):
    positions: List[OiRankPosition]


class OiRankPayload(BaseModel):
    status: str
    interval: str
    metric: str
    direction: str
    updated_at: Optional[datetime] = None
    refresh_started_at: Optional[datetime] = None
    data: Optional[OiRankData] = None
    error: Optional[str] = None


class OiRankResponse(BaseModel):
    data: OiRankPayload
    meta: Optional[ApiMeta] = None


class OiRankConfigPayload(BaseModel):
    refresh_interval_minutes: int = Field(..., ge=10, le=720)
    stale_ttl_minutes: int = Field(..., ge=10, le=1440)


class OiRankConfigView(BaseModel):
    refresh_interval_minutes: int
    stale_ttl_minutes: int


class OiRankConfigResponse(BaseModel):
    data: OiRankConfigView
    meta: Optional[ApiMeta] = None


def _meta(request: Request) -> ApiMeta:
    return ApiMeta(request_id=getattr(request.state, "request_id", None))


def _build_payload(result, limit: int) -> OiRankPayload:
    entries = result.entries
    data = None
    if entries:
        data = OiRankData(positions=[_to_position(entry) for entry in entries[:limit]])
    return OiRankPayload(
        status=result.status,
        interval=result.interval,
        metric=result.metric,
        direction=result.direction,
        updated_at=result.data_updated_at,
        refresh_started_at=result.refresh_started_at,
        data=data,
        error=result.last_error,
    )


def _to_position(entry: OiRankEntry) -> OiRankPosition:
    return OiRankPosition(
        symbol=entry.symbol,
        rank=entry.rank,
        delta=entry.delta,
        delta_pct=entry.delta_pct,
        current=entry.current,
        previous=entry.previous,
    )


@router.get("/top", response_model=OiRankResponse)
async def get_oi_top(
    request: Request,
    interval: str = "1h",
    limit: int = 5,
    metric: str = "abs",
) -> OiRankResponse:
    service = get_oi_rank_service()
    result = await service.get_rank(direction="top", interval=interval, limit=limit, metric=metric)
    payload = _build_payload(result, limit)
    return OiRankResponse(data=payload, meta=_meta(request))


@router.get("/low", response_model=OiRankResponse)
async def get_oi_low(
    request: Request,
    interval: str = "1h",
    limit: int = 5,
    metric: str = "abs",
) -> OiRankResponse:
    service = get_oi_rank_service()
    result = await service.get_rank(direction="low", interval=interval, limit=limit, metric=metric)
    payload = _build_payload(result, limit)
    return OiRankResponse(data=payload, meta=_meta(request))


@router.get("/config", response_model=OiRankConfigResponse)
async def get_oi_rank_config(request: Request) -> OiRankConfigResponse:
    service = get_oi_rank_service()
    config = await service.get_config()
    view = OiRankConfigView(
        refresh_interval_minutes=config.refresh_interval_minutes,
        stale_ttl_minutes=config.stale_ttl_minutes,
    )
    return OiRankConfigResponse(data=view, meta=_meta(request))


@router.put("/config", response_model=OiRankConfigResponse)
async def update_oi_rank_config(
    payload: OiRankConfigPayload,
    request: Request,
) -> OiRankConfigResponse:
    service = get_oi_rank_service()
    config = await service.update_config(
        refresh_interval_minutes=payload.refresh_interval_minutes,
        stale_ttl_minutes=payload.stale_ttl_minutes,
    )
    view = OiRankConfigView(
        refresh_interval_minutes=config.refresh_interval_minutes,
        stale_ttl_minutes=config.stale_ttl_minutes,
    )
    return OiRankConfigResponse(data=view, meta=_meta(request))

