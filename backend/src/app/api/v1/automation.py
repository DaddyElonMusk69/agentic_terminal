from datetime import datetime, timedelta, timezone
from uuid import uuid4
from typing import Dict, Optional, List

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field

from app.application.automation.runtime import AutomationRuntimeConfig, get_automation_runtime
from app.application.automation import topics
from app.application.automation.dependencies import (
    get_automation_config_service,
    get_automation_history_service,
)
from app.application.bus.outbox_service import OutboxService
from app.common.api import ApiMeta
from app.infrastructure.bus.outbox_repository import OutboxRepository
from app.infrastructure.db import get_sessionmaker
from app.realtime.hub import hub


router = APIRouter(prefix="/automation", tags=["automation"])


class AutomationStartRequest(BaseModel):
    execution_mode: str = Field("dry_run", min_length=1)
    ema_interval_seconds: int = Field(60, ge=5, le=3600)
    quant_interval_seconds: int = Field(60, ge=5, le=3600)
    provider: Optional[str] = None
    model: Optional[str] = None
    vegas_prompt_configs: Optional[Dict[str, int]] = None


class AutomationStateResponse(BaseModel):
    is_running: bool
    session_id: Optional[str] = None
    execution_mode: str
    ema_interval_seconds: int
    quant_interval_seconds: int
    provider: Optional[str] = None
    model: Optional[str] = None
    vegas_prompt_configs: Optional[Dict[str, int]] = None
    started_at: Optional[str] = None
    current_cycle: int = 0
    ema_cycles: int = 0
    quant_cycles: int = 0
    last_ema_cycle_at: Optional[str] = None
    last_quant_cycle_at: Optional[str] = None


class AutomationStateDataResponse(BaseModel):
    data: AutomationStateResponse
    meta: Optional[ApiMeta] = None


class AutomationConfigPayload(BaseModel):
    execution_mode: str = Field("dry_run", min_length=1)
    ema_interval_seconds: int = Field(60, ge=5, le=3600)
    quant_interval_seconds: int = Field(60, ge=5, le=3600)
    provider: Optional[str] = None
    model: Optional[str] = None
    vegas_prompt_configs: Optional[Dict[str, int]] = None


class AutomationConfigView(BaseModel):
    execution_mode: str
    ema_interval_seconds: int
    quant_interval_seconds: int
    provider: Optional[str] = None
    model: Optional[str] = None
    vegas_prompt_configs: Optional[Dict[str, int]] = None


class AutomationConfigResponse(BaseModel):
    data: AutomationConfigView
    meta: Optional[ApiMeta] = None


class OutboxPurgeResponse(BaseModel):
    purged: int
    cutoff: str
    hours: int


class OutboxPurgeDataResponse(BaseModel):
    data: OutboxPurgeResponse
    meta: Optional[ApiMeta] = None


class AutomationSessionSummary(BaseModel):
    id: str
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    execution_mode: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    total_cycles: int = 0
    total_trades: int = 0
    total_pnl: float = 0.0
    prompt_count: int = 0
    prompt_rate_per_hour: Optional[float] = None
    duration_seconds: Optional[int] = None


class AutomationSessionList(BaseModel):
    sessions: List[AutomationSessionSummary]
    total: int
    limit: int
    offset: int


class AutomationSessionListResponse(BaseModel):
    data: AutomationSessionList
    meta: Optional[ApiMeta] = None


class AutomationLogEntry(BaseModel):
    id: int
    session_id: str
    created_at: Optional[str] = None
    log_type: Optional[str] = None
    cycle_number: int = 0
    data: Optional[dict] = None


class AutomationTradeEntry(BaseModel):
    id: int
    session_id: str
    created_at: Optional[str] = None
    cycle_number: int = 0
    symbol: Optional[str] = None
    direction: Optional[str] = None
    action: Optional[str] = None
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    size_usd: Optional[float] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    status: Optional[str] = None
    closed_at: Optional[str] = None
    signal_data: Optional[dict] = None
    llm_reasoning: Optional[str] = None
    llm_response_full: Optional[str] = None
    order_id: Optional[str] = None
    fill_price: Optional[float] = None


class AutomationSessionDetail(BaseModel):
    session: AutomationSessionSummary
    logs: List[AutomationLogEntry]
    trades: List[AutomationTradeEntry]


class AutomationSessionDetailResponse(BaseModel):
    data: AutomationSessionDetail
    meta: Optional[ApiMeta] = None


class AutomationSessionExport(BaseModel):
    exported_at: str
    session: AutomationSessionSummary
    logs: List[AutomationLogEntry]
    trades: List[AutomationTradeEntry]


class AutomationSessionExportResponse(BaseModel):
    data: AutomationSessionExport
    meta: Optional[ApiMeta] = None


class AutomationSessionDeleteResponse(BaseModel):
    data: dict
    meta: Optional[ApiMeta] = None


def _meta(request: Request) -> ApiMeta:
    return ApiMeta(request_id=getattr(request.state, "request_id", None))


def _format_dt(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _duration_seconds(started_at: Optional[datetime], ended_at: Optional[datetime]) -> Optional[int]:
    if started_at is None:
        return None
    start = started_at
    end = ended_at or datetime.now(timezone.utc)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    elapsed = (end - start).total_seconds()
    if elapsed < 0:
        return None
    return int(elapsed)


def _prompt_rate_per_hour(
    started_at: Optional[datetime],
    ended_at: Optional[datetime],
    prompt_count: int,
) -> Optional[float]:
    duration = _duration_seconds(started_at, ended_at)
    if duration is None or duration <= 0:
        return None
    hours = duration / 3600
    if hours <= 0:
        return None
    return float(prompt_count) / hours


def _to_session_summary(session) -> AutomationSessionSummary:
    return AutomationSessionSummary(
        id=session.id,
        started_at=_format_dt(session.started_at),
        ended_at=_format_dt(session.ended_at),
        execution_mode=session.execution_mode,
        provider=session.provider,
        model=session.model,
        total_cycles=session.total_cycles or 0,
        total_trades=session.total_trades or 0,
        total_pnl=float(session.total_pnl or 0),
        prompt_count=session.prompt_count or 0,
        prompt_rate_per_hour=_prompt_rate_per_hour(
            session.started_at,
            session.ended_at,
            session.prompt_count or 0,
        ),
        duration_seconds=_duration_seconds(session.started_at, session.ended_at),
    )


def _to_log_entry(log) -> AutomationLogEntry:
    return AutomationLogEntry(
        id=log.id,
        session_id=log.session_id,
        created_at=_format_dt(log.created_at),
        log_type=log.log_type,
        cycle_number=log.cycle_number or 0,
        data=log.data or None,
    )


def _to_trade_entry(trade) -> AutomationTradeEntry:
    return AutomationTradeEntry(
        id=trade.id,
        session_id=trade.session_id,
        created_at=_format_dt(trade.created_at),
        cycle_number=trade.cycle_number or 0,
        symbol=trade.symbol,
        direction=trade.direction,
        action=trade.action,
        entry_price=trade.entry_price,
        exit_price=trade.exit_price,
        size_usd=trade.size_usd,
        pnl=trade.pnl,
        pnl_pct=trade.pnl_pct,
        status=trade.status,
        closed_at=_format_dt(trade.closed_at),
        signal_data=trade.signal_data,
        llm_reasoning=trade.llm_reasoning,
        llm_response_full=trade.llm_response_full,
        order_id=trade.order_id,
        fill_price=trade.fill_price,
    )


def _resolve_total_cycles(snapshot: dict) -> int:
    candidates = [
        snapshot.get("current_cycle"),
        snapshot.get("ema_cycles"),
        snapshot.get("quant_cycles"),
    ]
    values = [value for value in candidates if isinstance(value, int)]
    return max(values) if values else 0


@router.get("/config", response_model=AutomationConfigResponse)
async def get_automation_config(request: Request) -> AutomationConfigResponse:
    service = get_automation_config_service()
    config = await service.get_config()
    view = AutomationConfigView(
        execution_mode=config.execution_mode,
        ema_interval_seconds=config.ema_interval_seconds,
        quant_interval_seconds=config.quant_interval_seconds,
        provider=config.provider,
        model=config.model,
        vegas_prompt_configs=config.vegas_prompt_configs,
    )
    return AutomationConfigResponse(data=view, meta=_meta(request))


@router.put("/config", response_model=AutomationConfigResponse)
async def update_automation_config(
    payload: AutomationConfigPayload,
    request: Request,
) -> AutomationConfigResponse:
    service = get_automation_config_service()
    config = await service.update_config(
        execution_mode=payload.execution_mode,
        ema_interval_seconds=payload.ema_interval_seconds,
        quant_interval_seconds=payload.quant_interval_seconds,
        provider=payload.provider,
        model=payload.model,
        vegas_prompt_configs=payload.vegas_prompt_configs,
    )
    view = AutomationConfigView(
        execution_mode=config.execution_mode,
        ema_interval_seconds=config.ema_interval_seconds,
        quant_interval_seconds=config.quant_interval_seconds,
        provider=config.provider,
        model=config.model,
        vegas_prompt_configs=config.vegas_prompt_configs,
    )
    return AutomationConfigResponse(data=view, meta=_meta(request))


@router.get("/state", response_model=AutomationStateDataResponse)
async def get_state(request: Request) -> AutomationStateDataResponse:
    runtime = get_automation_runtime()
    state = AutomationStateResponse(**runtime.snapshot())
    return AutomationStateDataResponse(data=state, meta=_meta(request))


@router.post("/start", response_model=AutomationStateDataResponse)
async def start_automation(
    payload: AutomationStartRequest,
    request: Request,
) -> AutomationStateDataResponse:
    config_service = get_automation_config_service()
    config = await config_service.update_config(
        execution_mode=payload.execution_mode,
        ema_interval_seconds=payload.ema_interval_seconds,
        quant_interval_seconds=payload.quant_interval_seconds,
        provider=payload.provider,
        model=payload.model,
        vegas_prompt_configs=payload.vegas_prompt_configs,
    )
    session_id = str(uuid4())
    history_service = get_automation_history_service()
    await history_service.start_session(
        session_id=session_id,
        execution_mode=config.execution_mode,
        provider=config.provider,
        model=config.model,
        config_snapshot={
            "execution_mode": config.execution_mode,
            "ema_interval_seconds": config.ema_interval_seconds,
            "quant_interval_seconds": config.quant_interval_seconds,
            "provider": config.provider,
            "model": config.model,
            "vegas_prompt_configs": config.vegas_prompt_configs,
        },
    )
    runtime = get_automation_runtime()
    try:
        state = await runtime.start(
            AutomationRuntimeConfig(
                execution_mode=config.execution_mode,
                ema_interval_seconds=config.ema_interval_seconds,
                quant_interval_seconds=config.quant_interval_seconds,
                provider=config.provider,
                model=config.model,
                vegas_prompt_configs=config.vegas_prompt_configs,
                session_id=session_id,
            )
        )
    except Exception:
        await history_service.end_session(session_id=session_id, total_cycles=0)
        raise
    session_id = state.get("session_id") or session_id
    config_payload = {
        "execution_mode": config.execution_mode,
        "ema_interval_seconds": config.ema_interval_seconds,
        "quant_interval_seconds": config.quant_interval_seconds,
        "provider": config.provider,
        "model": config.model,
        "vegas_prompt_configs": config.vegas_prompt_configs,
        "started_at": state.get("started_at"),
        "session_id": session_id,
    }
    await hub.emit_topic(
        "automation.session.started",
        config_payload,
        request_id=getattr(request.state, "request_id", None),
    )
    await hub.emit_topic(
        "automation.session.config",
        config_payload,
        request_id=getattr(request.state, "request_id", None),
    )
    await hub.emit_topic(
        topics.PIPELINE_STARTED,
        config_payload,
        request_id=getattr(request.state, "request_id", None),
    )
    return AutomationStateDataResponse(data=AutomationStateResponse(**state), meta=_meta(request))


@router.post("/stop", response_model=AutomationStateDataResponse)
async def stop_automation(request: Request) -> AutomationStateDataResponse:
    runtime = get_automation_runtime()
    pre_state = runtime.snapshot()
    state = await runtime.stop()
    session_id = pre_state.get("session_id") or state.get("session_id")
    if pre_state.get("is_running") and session_id:
        history_service = get_automation_history_service()
        await history_service.end_session(
            session_id=session_id,
            total_cycles=_resolve_total_cycles(pre_state),
        )
    purged = 0
    if session_id:
        repository = OutboxRepository(get_sessionmaker())
        purged = await repository.delete_by_session_id(session_id)
    await hub.emit_topic(
        "automation.session.stopped",
        {
            "stopped_at": datetime.now(timezone.utc).isoformat(),
            "session_id": state.get("session_id"),
        },
        request_id=getattr(request.state, "request_id", None),
    )
    await hub.emit_topic(
        "automation.session.purged",
        {
            "purged": purged,
            "session_id": state.get("session_id"),
        },
        request_id=getattr(request.state, "request_id", None),
    )
    await hub.emit_topic(
        topics.PIPELINE_STOPPED,
        {
            "stopped_at": datetime.now(timezone.utc).isoformat(),
            "session_id": state.get("session_id"),
        },
        request_id=getattr(request.state, "request_id", None),
    )
    return AutomationStateDataResponse(data=AutomationStateResponse(**state), meta=_meta(request))


@router.post("/outbox/purge", response_model=OutboxPurgeDataResponse)
async def purge_outbox(request: Request) -> OutboxPurgeDataResponse:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=6)
    repository = OutboxRepository(get_sessionmaker())
    purged = await repository.delete_older_than(cutoff, statuses=("processed", "failed"))

    runtime = get_automation_runtime()
    session_id = runtime.snapshot().get("session_id")
    outbox = OutboxService(repository)
    payload = {
        "event": "outbox_purge_manual",
        "data": {
            "purged": purged,
            "cutoff_hours": 6,
        },
    }
    if session_id:
        payload["session_id"] = session_id
    await outbox.enqueue_event("scanner.ema.log", payload)

    return OutboxPurgeDataResponse(
        data=OutboxPurgeResponse(
            purged=purged,
            cutoff=cutoff.isoformat(),
            hours=6,
        ),
        meta=_meta(request),
    )


@router.get("/sessions", response_model=AutomationSessionListResponse)
async def list_sessions(
    request: Request,
    limit: int = 50,
    offset: int = 0,
) -> AutomationSessionListResponse:
    history_service = get_automation_history_service()
    sessions, total = await history_service.list_sessions(limit=limit, offset=offset)
    payload = AutomationSessionList(
        sessions=[_to_session_summary(session) for session in sessions],
        total=total,
        limit=limit,
        offset=offset,
    )
    return AutomationSessionListResponse(data=payload, meta=_meta(request))


@router.get("/sessions/{session_id}", response_model=AutomationSessionDetailResponse)
async def get_session_detail(
    session_id: str,
    request: Request,
    log_limit: int = 1000,
    log_offset: int = 0,
) -> AutomationSessionDetailResponse:
    history_service = get_automation_history_service()
    session, logs, trades = await history_service.get_session_detail(
        session_id=session_id,
        log_limit=log_limit,
        log_offset=log_offset,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    payload = AutomationSessionDetail(
        session=_to_session_summary(session),
        logs=[_to_log_entry(log) for log in logs],
        trades=[_to_trade_entry(trade) for trade in trades],
    )
    return AutomationSessionDetailResponse(data=payload, meta=_meta(request))


@router.get("/sessions/{session_id}/export", response_model=AutomationSessionExportResponse)
async def export_session(
    session_id: str,
    request: Request,
) -> AutomationSessionExportResponse:
    history_service = get_automation_history_service()
    session, logs, trades = await history_service.get_session_detail_all(session_id=session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    payload = AutomationSessionExport(
        exported_at=datetime.now(timezone.utc).isoformat(),
        session=_to_session_summary(session),
        logs=[_to_log_entry(log) for log in logs],
        trades=[_to_trade_entry(trade) for trade in trades],
    )
    return AutomationSessionExportResponse(data=payload, meta=_meta(request))


@router.delete("/sessions/{session_id}", response_model=AutomationSessionDeleteResponse)
async def delete_session(
    session_id: str,
    request: Request,
) -> AutomationSessionDeleteResponse:
    history_service = get_automation_history_service()
    deleted = await history_service.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return AutomationSessionDeleteResponse(data={"deleted": True}, meta=_meta(request))
