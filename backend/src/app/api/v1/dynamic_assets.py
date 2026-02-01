from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.application.dynamic_assets.dependencies import get_dynamic_assets_service
from app.common.api import ApiMeta


router = APIRouter(prefix="/market", tags=["market-settings"])


class Ai500Source(BaseModel):
    enabled: bool = False
    limit: int = Field(10, ge=1)


class Ai300Source(BaseModel):
    enabled: bool = False
    limit: int = Field(20, ge=1)
    level: str = ""


class OiSource(BaseModel):
    enabled: bool = False
    limit: int = Field(20, ge=1)
    duration: str = "1h"


class DynamicSources(BaseModel):
    ai500: Ai500Source = Field(default_factory=Ai500Source)
    ai300: Ai300Source = Field(default_factory=Ai300Source)
    oi_top: OiSource = Field(default_factory=OiSource)
    oi_low: OiSource = Field(default_factory=OiSource)


class DynamicAssetsConfigPayload(BaseModel):
    enabled: bool
    refresh_interval_seconds: int = Field(..., ge=60, le=3600)
    sources: Optional[DynamicSources] = None
    api_key: Optional[str] = None


class DynamicAssetsTestPayload(BaseModel):
    sources: DynamicSources
    api_key: Optional[str] = None


class DynamicAssetsConfigView(BaseModel):
    enabled: bool
    api_key_present: bool
    refresh_interval_seconds: int
    sources: DynamicSources
    is_binance_active: bool


class DynamicAssetsConfigResponse(BaseModel):
    data: DynamicAssetsConfigView
    meta: Optional[ApiMeta] = None


class DynamicAssetsTestResponse(BaseModel):
    data: Dict[str, Any]
    meta: Optional[ApiMeta] = None


def _meta(request: Request) -> ApiMeta:
    return ApiMeta(request_id=getattr(request.state, "request_id", None))


@router.get("/dynamic-assets", response_model=DynamicAssetsConfigResponse)
async def get_dynamic_assets_config(request: Request) -> DynamicAssetsConfigResponse:
    service = get_dynamic_assets_service()
    config = await service.get_config()
    is_binance_active = await service.is_binance_active()
    view = DynamicAssetsConfigView(
        enabled=config.enabled,
        api_key_present=bool(config.api_key),
        refresh_interval_seconds=config.refresh_interval_seconds,
        sources=DynamicSources.model_validate(config.sources),
        is_binance_active=is_binance_active,
    )
    return DynamicAssetsConfigResponse(data=view, meta=_meta(request))


@router.put("/dynamic-assets", response_model=DynamicAssetsConfigResponse)
async def update_dynamic_assets_config(
    payload: DynamicAssetsConfigPayload,
    request: Request,
) -> DynamicAssetsConfigResponse:
    service = get_dynamic_assets_service()
    update_api_key = "api_key" in payload.model_fields_set
    config = await service.update_config(
        enabled=payload.enabled,
        sources=payload.sources.model_dump() if payload.sources is not None else None,
        refresh_interval_seconds=payload.refresh_interval_seconds,
        api_key=payload.api_key,
        update_api_key=update_api_key,
    )
    is_binance_active = await service.is_binance_active()
    view = DynamicAssetsConfigView(
        enabled=config.enabled,
        api_key_present=bool(config.api_key),
        refresh_interval_seconds=config.refresh_interval_seconds,
        sources=DynamicSources.model_validate(config.sources),
        is_binance_active=is_binance_active,
    )
    return DynamicAssetsConfigResponse(data=view, meta=_meta(request))


@router.post("/dynamic-assets/test", response_model=DynamicAssetsTestResponse)
async def test_dynamic_assets(payload: DynamicAssetsTestPayload, request: Request) -> DynamicAssetsTestResponse:
    service = get_dynamic_assets_service()
    assets = await service.test_fetch(
        sources=payload.sources.model_dump(),
        api_key=payload.api_key,
    )
    return DynamicAssetsTestResponse(
        data={"assets": assets, "count": len(assets)},
        meta=_meta(request),
    )
