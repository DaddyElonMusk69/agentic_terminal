from typing import List, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.application.trade_guard.dependencies import get_trade_guard_service
from app.common.api import ApiMeta
from app.domain.trade_guard.models import LeverageTier, PositionTierRange, TradeGuardConfig


router = APIRouter(prefix="/trade-guard", tags=["trade-guard"])


class LeverageTierPayload(BaseModel):
    leverage: int = Field(1, ge=1)
    symbols: List[str] = Field(default_factory=list)


class PositionTierRangePayload(BaseModel):
    tier: int = Field(1, ge=1)
    min_pct: float = Field(0.0, ge=0.0)
    max_pct: float = Field(1.0, ge=0.0)


class TradeGuardConfigPayload(BaseModel):
    min_confidence: float = Field(60.0, ge=0.0, le=100.0)
    min_position_size: float = Field(10.0, ge=0.0)
    sl_min_roe: float = Field(0.03, ge=0.0)
    sl_max_roe: float = Field(0.05, ge=0.0)
    tp_min_roe: float = Field(0.05, ge=0.0)
    tp_max_roe: float = Field(0.2, ge=0.0)
    dust_threshold_usd: float = Field(10.0, ge=0.0)
    default_leverage: int = Field(1, ge=1, le=5)
    leverage_tiers: List[LeverageTierPayload] = Field(default_factory=list)
    position_tier_ranges: List[PositionTierRangePayload] = Field(default_factory=list)


class TradeGuardConfigView(BaseModel):
    min_confidence: float
    min_position_size: float
    sl_min_roe: float
    sl_max_roe: float
    tp_min_roe: float
    tp_max_roe: float
    dust_threshold_usd: float
    default_leverage: int
    leverage_tiers: List[LeverageTierPayload]
    position_tier_ranges: List[PositionTierRangePayload]


class TradeGuardConfigResponse(BaseModel):
    data: TradeGuardConfigView
    meta: Optional[ApiMeta] = None


def _meta(request: Request) -> ApiMeta:
    return ApiMeta(request_id=getattr(request.state, "request_id", None))


def _to_view(config: TradeGuardConfig) -> TradeGuardConfigView:
    return TradeGuardConfigView(
        min_confidence=config.min_confidence,
        min_position_size=config.min_position_size,
        sl_min_roe=config.sl_min_roe,
        sl_max_roe=config.sl_max_roe,
        tp_min_roe=config.tp_min_roe,
        tp_max_roe=config.tp_max_roe,
        dust_threshold_usd=config.dust_threshold_usd,
        default_leverage=config.default_leverage,
        leverage_tiers=[
            LeverageTierPayload(leverage=tier.leverage, symbols=tier.symbols)
            for tier in config.leverage_tiers
        ],
        position_tier_ranges=[
            PositionTierRangePayload(
                tier=tier.tier,
                min_pct=tier.min_pct,
                max_pct=tier.max_pct,
            )
            for tier in config.position_tier_ranges
        ],
    )


@router.get("/config", response_model=TradeGuardConfigResponse)
async def get_trade_guard_config(request: Request) -> TradeGuardConfigResponse:
    service = get_trade_guard_service()
    config = await service.get_config()
    return TradeGuardConfigResponse(data=_to_view(config), meta=_meta(request))


@router.put("/config", response_model=TradeGuardConfigResponse)
async def update_trade_guard_config(
    payload: TradeGuardConfigPayload,
    request: Request,
) -> TradeGuardConfigResponse:
    service = get_trade_guard_service()
    config = TradeGuardConfig(
        min_confidence=payload.min_confidence,
        min_position_size=payload.min_position_size,
        sl_min_roe=payload.sl_min_roe,
        sl_max_roe=payload.sl_max_roe,
        tp_min_roe=payload.tp_min_roe,
        tp_max_roe=payload.tp_max_roe,
        dust_threshold_usd=payload.dust_threshold_usd,
        default_leverage=payload.default_leverage,
        leverage_tiers=[
            LeverageTier(leverage=item.leverage, symbols=item.symbols)
            for item in payload.leverage_tiers
        ],
        position_tier_ranges=[
            PositionTierRange(tier=item.tier, min_pct=item.min_pct, max_pct=item.max_pct)
            for item in payload.position_tier_ranges
        ],
    )
    updated = await service.update_config(config)
    return TradeGuardConfigResponse(data=_to_view(updated), meta=_meta(request))
