from __future__ import annotations

import asyncio
import base64
from typing import List, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.application.chart_preview.dependencies import get_chart_preview_service
from app.common.api import ApiMeta
from app.common.errors import AppError
from app.infrastructure.external.binance_client import BinanceClient


router = APIRouter(prefix="/agent", tags=["agent"])


class ChartPreviewRequest(BaseModel):
    ticker: Optional[str] = "BTC"
    interval: str = Field(..., min_length=1)
    candles: int = Field(50, ge=1, le=2000)
    emas: Optional[List[int]] = None
    show_bb: bool = True
    show_atr: bool = True
    bb_length: int = Field(20, ge=1)
    bb_std: float = Field(2.0, gt=0)


class ChartPreviewPayload(BaseModel):
    chart_base64: str
    symbol: str
    interval: str
    candles: int


class ChartPreviewResponse(BaseModel):
    data: ChartPreviewPayload
    meta: Optional[ApiMeta] = None


def _meta(request: Request) -> ApiMeta:
    return ApiMeta(request_id=getattr(request.state, "request_id", None))


@router.post("/preview-chart", response_model=ChartPreviewResponse)
async def preview_chart(
    payload: ChartPreviewRequest,
    request: Request,
) -> ChartPreviewResponse:
    interval = payload.interval.strip().lower()
    if not interval:
        raise AppError(code="interval_required", message="Interval is required")

    symbol = (payload.ticker or "BTC").strip().upper() or "BTC"
    candle_limit = int(payload.candles) if payload.candles else 50
    candle_limit = max(1, min(candle_limit, BinanceClient.MAX_KLINES_LIMIT))
    ema_list = [int(value) for value in (payload.emas or []) if isinstance(value, (int, float))]

    service = get_chart_preview_service()
    image_bytes = await asyncio.to_thread(
        service.render_preview,
        symbol,
        interval,
        candle_limit,
        ema_list,
        payload.show_bb,
        payload.show_atr,
        payload.bb_length,
        payload.bb_std,
    )
    if not image_bytes:
        error_message = service.consume_last_error() or "Chart preview failed"
        raise AppError(code="chart_preview_failed", message=error_message)

    chart_base64 = base64.b64encode(image_bytes).decode("ascii")
    return ChartPreviewResponse(
        data=ChartPreviewPayload(
            chart_base64=chart_base64,
            symbol=symbol,
            interval=interval,
            candles=candle_limit,
        ),
        meta=_meta(request),
    )
