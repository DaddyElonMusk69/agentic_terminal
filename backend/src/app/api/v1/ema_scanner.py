from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.application.ema_scanner.dependencies import (
    get_ema_config_service,
    get_ema_scan_runner,
)
from app.application.ema_scanner.runner import EmaConfigLoadError, EmaScanRunError
from app.application.ema_scanner.runner import (
    EmaScanAlreadyRunningError,
    EmaScanCancelledError,
)
from app.application.ema_state_manager.dependencies import (
    get_ema_state_config_service,
    get_ema_state_manager_service,
)
from app.application.ema_state_manager.presenter import build_vegas_state_payload
from app.application.scanner_results.dependencies import get_scanner_results_service
from app.common.api import ApiMeta
from app.realtime.hub import hub


router = APIRouter(prefix="/scanner/ema", tags=["ema-scanner"])


class EmaLineResponse(BaseModel):
    id: int
    length: int


class EmaScannerConfigResponse(BaseModel):
    ema_lines: List[EmaLineResponse]
    tolerance_pct: float
    available_intervals: List[str] = Field(default_factory=list)
    scan_intervals: List[str] = Field(default_factory=list)


class EmaScannerConfigDataResponse(BaseModel):
    data: EmaScannerConfigResponse
    meta: Optional[ApiMeta] = None


class EmaLineCreateRequest(BaseModel):
    length: int = Field(..., ge=1, le=5000)


class EmaConfigUpdateRequest(BaseModel):
    tolerance_pct: float | None = Field(default=None, ge=0.05, le=2.0)
    scan_intervals: List[str] | None = None


class ScannerVoteResponse(BaseModel):
    interval: str
    param: Optional[str | int] = None


class ScannerResultResponse(BaseModel):
    id: Optional[int] = None
    ticker: str
    votes: int = 0
    intervals: List[str] = Field(default_factory=list)
    ema_votes: List[ScannerVoteResponse] = Field(default_factory=list)
    bb_votes: List[ScannerVoteResponse] = Field(default_factory=list)
    chart_data: Optional[Dict[str, object]] = None


class EmaScanResults(BaseModel):
    results: List[ScannerResultResponse]


class EmaScanResultsResponse(BaseModel):
    data: EmaScanResults
    meta: Optional[ApiMeta] = None


class EmaScanCalendarResponse(BaseModel):
    data: Dict[str, int]
    meta: Optional[ApiMeta] = None


class EmaScanLatestPayload(BaseModel):
    date: Optional[str] = None
    results: List[ScannerResultResponse] = Field(default_factory=list)


class EmaScanLatestResponse(BaseModel):
    data: EmaScanLatestPayload
    meta: Optional[ApiMeta] = None


class EmaScanImportPayload(BaseModel):
    count: int


class EmaScanImportResponse(BaseModel):
    data: EmaScanImportPayload
    meta: Optional[ApiMeta] = None


class EmaScanDeletePayload(BaseModel):
    success: bool


class EmaScanDeleteResponse(BaseModel):
    data: EmaScanDeletePayload
    meta: Optional[ApiMeta] = None


class EmaScanControlPayload(BaseModel):
    running: bool
    stop_requested: bool = False


class EmaScanControlResponse(BaseModel):
    data: EmaScanControlPayload
    meta: Optional[ApiMeta] = None


class EmaStatePayload(BaseModel):
    states: List[Dict[str, object]]


class EmaStateResponse(BaseModel):
    data: EmaStatePayload
    meta: Optional[ApiMeta] = None


class EmaStateManagerConfigPayload(BaseModel):
    min_resonance: int = Field(..., ge=1, le=5)
    ema_resonance_cooldown_seconds: int = Field(..., ge=60, le=3600)
    bb_rejection_cooldown_seconds: int = Field(..., ge=60, le=3600)
    bb_exit_warning_cooldown_seconds: int = Field(..., ge=60, le=3600)
    position_check_interval_seconds: int = Field(..., ge=60, le=3600)
    bb_rejection_min_touches: int = Field(..., ge=1, le=30)
    bb_htf_min_interval_minutes: int = Field(..., ge=15)
    new_resonance_min_touches: int = Field(..., ge=1, le=30)
    emit_new_resonance: Optional[bool] = None
    emit_resonance_increase: Optional[bool] = None
    emit_structure_shift: Optional[bool] = None
    emit_resonance_refresh: Optional[bool] = None
    emit_bb_rejection_upper: Optional[bool] = None
    emit_bb_rejection_lower: Optional[bool] = None
    emit_position_management: Optional[bool] = None
    emit_bb_exit_warning: Optional[bool] = None


class EmaStateManagerConfigView(BaseModel):
    min_resonance: int
    ema_resonance_cooldown_seconds: int
    bb_rejection_cooldown_seconds: int
    bb_exit_warning_cooldown_seconds: int
    position_check_interval_seconds: int
    bb_rejection_min_touches: int
    bb_htf_min_interval_minutes: int
    new_resonance_min_touches: int
    emit_new_resonance: bool
    emit_resonance_increase: bool
    emit_structure_shift: bool
    emit_resonance_refresh: bool
    emit_bb_rejection_upper: bool
    emit_bb_rejection_lower: bool
    emit_position_management: bool
    emit_bb_exit_warning: bool


class EmaStateManagerConfigResponse(BaseModel):
    data: EmaStateManagerConfigView
    meta: Optional[ApiMeta] = None


def _meta(request: Request) -> ApiMeta:
    return ApiMeta(request_id=getattr(request.state, "request_id", None))


def _config_response(
    ema_lines: List[EmaLineResponse],
    tolerance_pct: float,
    available_intervals: List[str],
    scan_intervals: List[str],
) -> EmaScannerConfigResponse:
    return EmaScannerConfigResponse(
        ema_lines=ema_lines,
        tolerance_pct=tolerance_pct,
        available_intervals=available_intervals,
        scan_intervals=scan_intervals,
    )


async def _emit_log(request: Request, event: str, data: Optional[dict] = None) -> None:
    payload = {"event": event, "data": data or {}}
    if isinstance(data, dict):
        cycle_number = data.get("cycle_number")
        if cycle_number is not None:
            payload["cycle_number"] = cycle_number
    await hub.emit_topic(
        "scanner.ema.log",
        payload,
        request_id=getattr(request.state, "request_id", None),
    )


async def _emit_state(request: Request, payload: dict) -> None:
    await hub.emit_topic(
        "scanner.ema.state",
        payload,
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/state", response_model=EmaStateResponse)
async def get_state(request: Request) -> EmaStateResponse:
    service = get_ema_state_manager_service()
    config = await service.get_config()
    payload = build_vegas_state_payload(service.get_all_states(), config)
    return EmaStateResponse(
        data=EmaStatePayload(states=payload.get("states", [])),
        meta=_meta(request),
    )


@router.post("/state/clear", response_model=EmaStateResponse)
async def clear_state(request: Request) -> EmaStateResponse:
    service = get_ema_state_manager_service()
    service.clear_all_states()
    config = await service.get_config()
    payload = build_vegas_state_payload(service.get_all_states(), config)
    await _emit_state(request, payload)
    return EmaStateResponse(
        data=EmaStatePayload(states=payload.get("states", [])),
        meta=_meta(request),
    )


@router.get("/state/config", response_model=EmaStateManagerConfigResponse)
async def get_state_config(request: Request) -> EmaStateManagerConfigResponse:
    service = get_ema_state_config_service()
    config = await service.get_config()
    view = EmaStateManagerConfigView(
        min_resonance=config.min_resonance,
        ema_resonance_cooldown_seconds=config.ema_resonance_cooldown_seconds,
        bb_rejection_cooldown_seconds=config.bb_rejection_cooldown_seconds,
        bb_exit_warning_cooldown_seconds=config.bb_exit_warning_cooldown_seconds,
        position_check_interval_seconds=config.position_check_interval_seconds,
        bb_rejection_min_touches=config.bb_rejection_min_touches,
        bb_htf_min_interval_minutes=config.bb_htf_min_interval_minutes,
        new_resonance_min_touches=config.new_resonance_min_touches,
        emit_new_resonance=config.emit_new_resonance,
        emit_resonance_increase=config.emit_resonance_increase,
        emit_structure_shift=config.emit_structure_shift,
        emit_resonance_refresh=config.emit_resonance_refresh,
        emit_bb_rejection_upper=config.emit_bb_rejection_upper,
        emit_bb_rejection_lower=config.emit_bb_rejection_lower,
        emit_position_management=config.emit_position_management,
        emit_bb_exit_warning=config.emit_bb_exit_warning,
    )
    return EmaStateManagerConfigResponse(data=view, meta=_meta(request))


@router.put("/state/config", response_model=EmaStateManagerConfigResponse)
async def update_state_config(
    payload: EmaStateManagerConfigPayload,
    request: Request,
) -> EmaStateManagerConfigResponse:
    service = get_ema_state_config_service()
    current = await service.get_config()
    config = await service.update_config(
        min_resonance=payload.min_resonance,
        ema_resonance_cooldown_seconds=payload.ema_resonance_cooldown_seconds,
        bb_rejection_cooldown_seconds=payload.bb_rejection_cooldown_seconds,
        bb_exit_warning_cooldown_seconds=payload.bb_exit_warning_cooldown_seconds,
        position_check_interval_seconds=payload.position_check_interval_seconds,
        bb_rejection_min_touches=payload.bb_rejection_min_touches,
        bb_htf_min_interval_minutes=payload.bb_htf_min_interval_minutes,
        new_resonance_min_touches=payload.new_resonance_min_touches,
        emit_new_resonance=(
            payload.emit_new_resonance
            if payload.emit_new_resonance is not None
            else current.emit_new_resonance
        ),
        emit_resonance_increase=(
            payload.emit_resonance_increase
            if payload.emit_resonance_increase is not None
            else current.emit_resonance_increase
        ),
        emit_structure_shift=(
            payload.emit_structure_shift
            if payload.emit_structure_shift is not None
            else current.emit_structure_shift
        ),
        emit_resonance_refresh=(
            payload.emit_resonance_refresh
            if payload.emit_resonance_refresh is not None
            else current.emit_resonance_refresh
        ),
        emit_bb_rejection_upper=(
            payload.emit_bb_rejection_upper
            if payload.emit_bb_rejection_upper is not None
            else current.emit_bb_rejection_upper
        ),
        emit_bb_rejection_lower=(
            payload.emit_bb_rejection_lower
            if payload.emit_bb_rejection_lower is not None
            else current.emit_bb_rejection_lower
        ),
        emit_position_management=(
            payload.emit_position_management
            if payload.emit_position_management is not None
            else current.emit_position_management
        ),
        emit_bb_exit_warning=(
            payload.emit_bb_exit_warning
            if payload.emit_bb_exit_warning is not None
            else current.emit_bb_exit_warning
        ),
    )
    view = EmaStateManagerConfigView(
        min_resonance=config.min_resonance,
        ema_resonance_cooldown_seconds=config.ema_resonance_cooldown_seconds,
        bb_rejection_cooldown_seconds=config.bb_rejection_cooldown_seconds,
        bb_exit_warning_cooldown_seconds=config.bb_exit_warning_cooldown_seconds,
        position_check_interval_seconds=config.position_check_interval_seconds,
        bb_rejection_min_touches=config.bb_rejection_min_touches,
        bb_htf_min_interval_minutes=config.bb_htf_min_interval_minutes,
        new_resonance_min_touches=config.new_resonance_min_touches,
        emit_new_resonance=config.emit_new_resonance,
        emit_resonance_increase=config.emit_resonance_increase,
        emit_structure_shift=config.emit_structure_shift,
        emit_resonance_refresh=config.emit_resonance_refresh,
        emit_bb_rejection_upper=config.emit_bb_rejection_upper,
        emit_bb_rejection_lower=config.emit_bb_rejection_lower,
        emit_position_management=config.emit_position_management,
        emit_bb_exit_warning=config.emit_bb_exit_warning,
    )
    return EmaStateManagerConfigResponse(data=view, meta=_meta(request))


@router.get("/config", response_model=EmaScannerConfigDataResponse)
async def get_config(request: Request) -> EmaScannerConfigDataResponse:
    service = get_ema_config_service()
    lines = await service.list_lines()
    tolerance = await service.get_tolerance_value()
    available_intervals = await service.list_available_intervals()
    scan_intervals = await service.get_effective_scan_intervals()
    payload = [EmaLineResponse(id=line.id, length=line.length) for line in lines]
    return EmaScannerConfigDataResponse(
        data=_config_response(payload, tolerance, available_intervals, scan_intervals),
        meta=_meta(request),
    )


@router.put("/config", response_model=EmaScannerConfigDataResponse)
async def update_config(
    payload: EmaConfigUpdateRequest,
    request: Request,
) -> EmaScannerConfigDataResponse:
    service = get_ema_config_service()
    if payload.tolerance_pct is not None:
        await service.set_tolerance(payload.tolerance_pct)
    if payload.scan_intervals is not None:
        await service.update_scan_intervals(payload.scan_intervals)
    lines = await service.list_lines()
    tolerance = await service.get_tolerance_value()
    available_intervals = await service.list_available_intervals()
    scan_intervals = await service.get_effective_scan_intervals()
    line_payload = [EmaLineResponse(id=line.id, length=line.length) for line in lines]
    return EmaScannerConfigDataResponse(
        data=_config_response(line_payload, tolerance, available_intervals, scan_intervals),
        meta=_meta(request),
    )


@router.post("/lines", response_model=EmaScannerConfigDataResponse)
async def add_line(
    payload: EmaLineCreateRequest,
    request: Request,
) -> EmaScannerConfigDataResponse:
    service = get_ema_config_service()
    lines = await service.add_line(payload.length)
    tolerance = await service.get_tolerance_value()
    available_intervals = await service.list_available_intervals()
    scan_intervals = await service.get_effective_scan_intervals()
    line_payload = [EmaLineResponse(id=line.id, length=line.length) for line in lines]
    return EmaScannerConfigDataResponse(
        data=_config_response(line_payload, tolerance, available_intervals, scan_intervals),
        meta=_meta(request),
    )


@router.delete("/lines/{line_id}", response_model=EmaScannerConfigDataResponse)
async def remove_line(
    line_id: int,
    request: Request,
) -> EmaScannerConfigDataResponse:
    service = get_ema_config_service()
    lines = await service.remove_line(line_id)
    tolerance = await service.get_tolerance_value()
    available_intervals = await service.list_available_intervals()
    scan_intervals = await service.get_effective_scan_intervals()
    line_payload = [EmaLineResponse(id=line.id, length=line.length) for line in lines]
    return EmaScannerConfigDataResponse(
        data=_config_response(line_payload, tolerance, available_intervals, scan_intervals),
        meta=_meta(request),
    )


@router.get("/calendar", response_model=EmaScanCalendarResponse)
async def get_calendar(request: Request) -> EmaScanCalendarResponse:
    results_service = get_scanner_results_service()
    data = await results_service.get_calendar_data()
    return EmaScanCalendarResponse(data=data, meta=_meta(request))


@router.get("/history", response_model=EmaScanResultsResponse)
async def get_history(date: str, request: Request) -> EmaScanResultsResponse:
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD") from exc

    results_service = get_scanner_results_service()
    results = await results_service.get_results_by_date(target_date)
    return EmaScanResultsResponse(
        data=EmaScanResults(results=results),
        meta=_meta(request),
    )


@router.get("/latest", response_model=EmaScanLatestResponse)
async def get_latest(request: Request) -> EmaScanLatestResponse:
    results_service = get_scanner_results_service()
    latest_date, results = await results_service.get_latest_results()
    payload = EmaScanLatestPayload(
        date=latest_date.isoformat() if latest_date else None,
        results=results,
    )
    return EmaScanLatestResponse(data=payload, meta=_meta(request))


@router.delete("/result/{result_id}", response_model=EmaScanDeleteResponse)
async def delete_result(result_id: int, request: Request) -> EmaScanDeleteResponse:
    results_service = get_scanner_results_service()
    success = await results_service.delete_result(result_id)
    if not success:
        raise HTTPException(status_code=404, detail="Scan result not found")
    return EmaScanDeleteResponse(
        data=EmaScanDeletePayload(success=True),
        meta=_meta(request),
    )


@router.get("/export")
async def export_scan_results() -> Response:
    results_service = get_scanner_results_service()
    csv_content = await results_service.export_scan_results()
    headers = {"Content-Disposition": "attachment; filename=scan_results.csv"}
    return Response(content=csv_content, media_type="text/csv", headers=headers)


@router.post("/import", response_model=EmaScanImportResponse)
async def import_scan_results(
    request: Request,
    file: UploadFile = File(...),
) -> EmaScanImportResponse:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")
    content = await file.read()
    try:
        csv_content = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded") from exc

    results_service = get_scanner_results_service()
    try:
        count = await results_service.import_scan_results(csv_content)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid CSV format: {exc}") from exc
    return EmaScanImportResponse(
        data=EmaScanImportPayload(count=count),
        meta=_meta(request),
    )


@router.post("/run", response_model=EmaScanResultsResponse)
async def run_scan(request: Request) -> EmaScanResultsResponse:
    runner = get_ema_scan_runner()

    async def log_event(event: str, data: Optional[dict] = None) -> None:
        await _emit_log(request, event, data)

    async def emit_state(payload: dict) -> None:
        await _emit_state(request, payload)

    try:
        response_payload = await runner.run_scan(
            log_callback=log_event,
            state_callback=emit_state,
        )
    except EmaConfigLoadError as exc:
        raise HTTPException(status_code=500, detail="Failed to load EMA scanner config") from exc
    except EmaScanAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except EmaScanCancelledError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EmaScanRunError as exc:
        raise HTTPException(status_code=500, detail="EMA scan failed") from exc

    return EmaScanResultsResponse(
        data=EmaScanResults(results=response_payload),
        meta=_meta(request),
    )


@router.post("/stop", response_model=EmaScanControlResponse)
async def stop_scan(request: Request) -> EmaScanControlResponse:
    runner = get_ema_scan_runner()
    was_running = runner.is_running()
    stop_requested = runner.cancel_active_scan()

    if stop_requested:
        await _emit_log(
            request,
            "scan_cancel_requested",
            {"running": was_running},
        )

    return EmaScanControlResponse(
        data=EmaScanControlPayload(
            running=runner.is_running(),
            stop_requested=stop_requested,
        ),
        meta=_meta(request),
    )
