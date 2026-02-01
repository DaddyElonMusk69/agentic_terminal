from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.application.prompt_builder.dependencies import get_prompt_builder_service
from app.application.prompt_templates.dependencies import get_prompt_template_service
from app.application.quant_scanner.dependencies import get_quant_scanner_service
from app.application.market_settings.dependencies import get_market_settings_service
from app.common.api import ApiMeta
from app.common.errors import AppError
from app.domain.prompt_builder.models import ChartRequest, PromptBuildRequest


router = APIRouter(prefix="/agent/templates", tags=["agent-templates"])


class PromptTemplateView(BaseModel):
    id: int
    name: str
    intro: str
    response_format: str
    quant_fields: Optional[List[str]] = None
    chart_defaults: Optional[Dict[str, Any]] = None
    is_default: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PromptTemplateListResponse(BaseModel):
    data: List[PromptTemplateView]
    meta: Optional[ApiMeta] = None


class PromptTemplateResponse(BaseModel):
    data: PromptTemplateView
    meta: Optional[ApiMeta] = None


class PromptTemplateCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    intro: str = Field(..., min_length=1)
    response_format: str = Field(..., min_length=1)
    quant_fields: Optional[List[str]] = None
    chart_defaults: Optional[Dict[str, Any]] = None
    is_default: Optional[bool] = None


class PromptTemplateUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    intro: Optional[str] = None
    response_format: Optional[str] = None
    quant_fields: Optional[List[str]] = None
    chart_defaults: Optional[Dict[str, Any]] = None
    is_default: Optional[bool] = None


class ChartRequestPayload(BaseModel):
    interval: str = Field(..., min_length=1)
    candles: Optional[int] = None
    overlays: Optional[List[str]] = None


class PromptPreviewRequest(BaseModel):
    ticker: str = Field(..., min_length=1)
    intervals: Optional[List[str]] = None
    chart_requests: Optional[List[ChartRequestPayload]] = None


class PromptPreviewPayload(BaseModel):
    template_id: int
    template_name: str
    prompt_text: str
    data: Dict[str, Any]
    chart_items: List[Dict[str, Any]]
    created_at: str


class PromptPreviewResponse(BaseModel):
    data: PromptPreviewPayload
    meta: Optional[ApiMeta] = None


def _meta(request: Request) -> ApiMeta:
    return ApiMeta(request_id=getattr(request.state, "request_id", None))


_LEGACY_CHART_DEFAULT_KEYS = {
    "chart_snapshot_interval",
    "chart1_candles",
    "chart2_enabled",
    "chart2_interval",
    "chart2_candles",
    "show_ema",
    "show_vwap",
}


def _sanitize_chart_defaults(value: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    return {key: val for key, val in value.items() if key not in _LEGACY_CHART_DEFAULT_KEYS}


def _to_view(template) -> PromptTemplateView:
    return PromptTemplateView(
        id=template.id,
        name=template.name,
        intro=template.intro,
        response_format=template.response_format,
        quant_fields=template.quant_fields,
        chart_defaults=_sanitize_chart_defaults(template.chart_defaults),
        is_default=bool(template.is_default),
        created_at=template.created_at.isoformat() if template.created_at else None,
        updated_at=template.updated_at.isoformat() if template.updated_at else None,
    )


def _dedupe(values: List[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for value in values:
        item = str(value)
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def _build_chart_requests(
    chart_defaults: Optional[Dict[str, Any]],
    payload: PromptPreviewRequest,
    monitored_intervals: List[str],
) -> List[ChartRequest]:
    if payload.chart_requests:
        requests: List[ChartRequest] = []
        for item in payload.chart_requests:
            interval = _resolve_interval(item.interval, monitored_intervals)
            if not interval:
                continue
            requests.append(
                ChartRequest(
                    interval=interval,
                    candles=item.candles,
                    overlays=item.overlays,
                )
            )
        return requests

    defaults = chart_defaults or {}
    vegas_configs = defaults.get("vegas_interval_configs")
    requests: List[ChartRequest] = []

    interval_order: List[str] = []
    if isinstance(vegas_configs, dict) and vegas_configs:
        for interval in monitored_intervals:
            if interval in vegas_configs or interval.lower() in vegas_configs:
                interval_order.append(interval)
        if not interval_order:
            for key in vegas_configs.keys():
                interval_order.append(str(key))
    else:
        interval_order = list(monitored_intervals)

    if not interval_order:
        return []

    for interval in interval_order:
        candles = 50
        if isinstance(vegas_configs, dict):
            raw = vegas_configs.get(interval)
            if raw is None:
                raw = vegas_configs.get(interval.lower())
            try:
                mapped = int(raw)
            except (TypeError, ValueError):
                mapped = None
            if mapped and mapped > 0:
                candles = mapped
        requests.append(ChartRequest(interval=interval, candles=candles))

    return requests


def _resolve_interval(value: Any, monitored_intervals: List[str], fallback_index: int = 0) -> str:
    interval = str(value or "").strip()
    if interval and interval in monitored_intervals:
        return interval
    if monitored_intervals:
        if 0 <= fallback_index < len(monitored_intervals):
            return monitored_intervals[fallback_index]
        return monitored_intervals[0]
    return ""


def _split_symbol(symbol: str) -> tuple[str, Optional[str]]:
    if "/" in symbol:
        base, quote = symbol.split("/", 1)
        return base, quote
    if ":" in symbol:
        base, quote = symbol.split(":", 1)
        return base, quote
    return symbol, None


def _timeframe_minutes(timeframe: str) -> Optional[int]:
    if not timeframe:
        return None
    value = timeframe.strip().lower()
    if value.endswith("m") and value[:-1].isdigit():
        return int(value[:-1])
    if value.endswith("h") and value[:-1].isdigit():
        return int(value[:-1]) * 60
    if value.endswith("d") and value[:-1].isdigit():
        return int(value[:-1]) * 1440
    return None


def _select_primary_interval(intervals: List[str]) -> str:
    best: Optional[str] = None
    best_minutes: Optional[int] = None
    for interval in intervals:
        minutes = _timeframe_minutes(interval)
        if minutes is None:
            if best is None:
                best = interval
            continue
        if best_minutes is None or minutes > best_minutes:
            best = interval
            best_minutes = minutes
    return best or ""


@router.get("", response_model=PromptTemplateListResponse)
async def list_templates(request: Request) -> PromptTemplateListResponse:
    service = get_prompt_template_service()
    templates = await service.list_templates()
    payload = [_to_view(template) for template in templates]
    return PromptTemplateListResponse(data=payload, meta=_meta(request))


@router.post("", response_model=PromptTemplateResponse)
async def create_template(
    payload: PromptTemplateCreateRequest,
    request: Request,
) -> PromptTemplateResponse:
    service = get_prompt_template_service()
    chart_defaults = _sanitize_chart_defaults(payload.chart_defaults)
    try:
        template = await service.create_template(
            name=payload.name,
            intro=payload.intro,
            response_format=payload.response_format,
            quant_fields=payload.quant_fields,
            chart_defaults=chart_defaults,
            is_default=bool(payload.is_default),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PromptTemplateResponse(data=_to_view(template), meta=_meta(request))


@router.put("/{template_id}", response_model=PromptTemplateResponse)
async def update_template(
    template_id: int,
    payload: PromptTemplateUpdateRequest,
    request: Request,
) -> PromptTemplateResponse:
    service = get_prompt_template_service()
    fields = payload.model_dump(exclude_unset=True)
    if "chart_defaults" in fields:
        fields["chart_defaults"] = _sanitize_chart_defaults(fields.get("chart_defaults"))
    try:
        template = await service.update_template(template_id, fields)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PromptTemplateResponse(data=_to_view(template), meta=_meta(request))


@router.delete("/{template_id}")
async def delete_template(template_id: int, request: Request) -> dict:
    service = get_prompt_template_service()
    try:
        await service.delete_template(template_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"data": {"deleted": True}, "meta": _meta(request).model_dump()}


@router.post("/{template_id}/preview", response_model=PromptPreviewResponse)
async def preview_template(
    template_id: int,
    payload: PromptPreviewRequest,
    request: Request,
) -> PromptPreviewResponse:
    template_service = get_prompt_template_service()
    template = await template_service.get_template(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    ticker = payload.ticker.strip().upper()
    if not ticker:
        raise AppError(code="ticker_required", message="Ticker is required")

    market_service = get_market_settings_service()
    monitored_intervals = [item.strip() for item in await market_service.list_intervals() if item.strip()]
    chart_requests = _build_chart_requests(template.chart_defaults, payload, monitored_intervals)
    if payload.intervals:
        intervals = _dedupe(
            [
                interval.strip()
                for interval in payload.intervals
                if interval.strip() and interval.strip() in monitored_intervals
            ]
        )
    else:
        intervals = _dedupe([item.interval for item in chart_requests if item.interval])

    if not intervals:
        raise AppError(code="intervals_required", message="Intervals are required for preview")

    quant_service = get_quant_scanner_service()
    missing = [
        f"{ticker}@{interval}"
        for interval in intervals
        if quant_service.get_snapshot(ticker, interval) is None
    ]
    if missing:
        raise AppError(
            code="quant_snapshot_missing",
            message="Quant snapshots missing for preview",
            details={"missing": missing},
        )

    base, quote = _split_symbol(ticker)
    primary_interval = _select_primary_interval(intervals)
    build_request = PromptBuildRequest(
        request_id=str(uuid4()),
        template_id=template.id,
        trigger_reason="context_preview",
        tickers=[ticker],
        intervals=intervals,
        chart_requests=chart_requests,
        template_context={
            "ticker": base,
            "symbol": ticker,
            "quote": quote,
            "interval": primary_interval,
            "intervals": ", ".join(intervals),
            "active_intervals": ", ".join(intervals),
            "trigger_reason": "context_preview",
        },
    )

    prompt_builder = get_prompt_builder_service()
    result = await prompt_builder.build(build_request)

    return PromptPreviewResponse(
        data=PromptPreviewPayload(
            template_id=result.template_id,
            template_name=result.template_name,
            prompt_text=result.prompt_text,
            data=result.data,
            chart_items=result.chart_items,
            created_at=result.created_at.isoformat(),
        ),
        meta=_meta(request),
    )
