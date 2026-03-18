from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.application.quant_scanner.dependencies import get_quant_scan_runner
from app.application.quant_scanner.runner import (
    QuantConfigLoadError,
    QuantScanAlreadyRunningError,
    QuantScanCancelledError,
    QuantScanRunError,
)
from app.common.api import ApiMeta
from app.realtime.hub import hub


router = APIRouter(prefix="/scanner/quant", tags=["quant-scanner"])


class QuantScanResults(BaseModel):
    results: List[Dict[str, Any]]


class QuantScanResultsResponse(BaseModel):
    data: QuantScanResults
    meta: Optional[ApiMeta] = None


class QuantScanControlPayload(BaseModel):
    running: bool
    stop_requested: bool


class QuantScanControlResponse(BaseModel):
    data: QuantScanControlPayload
    meta: Optional[ApiMeta] = None


def _meta(request: Request) -> ApiMeta:
    return ApiMeta(request_id=getattr(request.state, "request_id", None))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


async def _emit_log(request: Request, message: str, log_type: str = "info") -> None:
    payload = {
        "message": message,
        "type": log_type,
        "timestamp": _now_iso(),
    }
    await hub.emit_topic(
        "scanner.quant.log",
        payload,
        request_id=getattr(request.state, "request_id", None),
    )


@router.post("/run", response_model=QuantScanResultsResponse)
async def run_quant_scan(request: Request) -> QuantScanResultsResponse:
    runner = get_quant_scan_runner()
    request_id = getattr(request.state, "request_id", None)

    async def log_event(message: str, log_type: str) -> None:
        await _emit_log(request, message, log_type)

    async def emit_signal(signal: dict) -> None:
        await hub.emit_topic(
            "scanner.quant.signal",
            signal,
            request_id=request_id,
        )

    async def emit_completed(payload: dict) -> None:
        await hub.emit_topic(
            "scanner.quant.completed",
            payload,
            request_id=request_id,
        )

    try:
        results = await runner.run_scan(
            log_callback=log_event,
            signal_callback=emit_signal,
            completed_callback=emit_completed,
        )
    except QuantConfigLoadError as exc:
        raise HTTPException(status_code=500, detail="Failed to load quant scanner config") from exc
    except QuantScanAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except QuantScanCancelledError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except QuantScanRunError as exc:
        raise HTTPException(status_code=500, detail="Quant scan failed") from exc

    return QuantScanResultsResponse(data=QuantScanResults(results=results), meta=_meta(request))


@router.post("/stop", response_model=QuantScanControlResponse)
async def stop_quant_scan(request: Request) -> QuantScanControlResponse:
    runner = get_quant_scan_runner()
    stop_requested = runner.cancel_active_scan()

    if stop_requested:
        await _emit_log(request, "Quant scan cancel requested.", "warning")

    return QuantScanControlResponse(
        data=QuantScanControlPayload(
            running=runner.is_running(),
            stop_requested=stop_requested,
        ),
        meta=_meta(request),
    )
