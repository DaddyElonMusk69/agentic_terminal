from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.common.api import ApiMeta
from app.settings import get_settings

router = APIRouter()


class HealthPayload(BaseModel):
    status: str
    service: str
    version: str
    time: str
    checks: Optional[dict] = None


class HealthResponse(BaseModel):
    data: HealthPayload
    meta: Optional[ApiMeta] = None


def _base_payload() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.service_name,
        "version": settings.version,
        "time": datetime.now(timezone.utc).isoformat(),
    }

def _meta(request: Request) -> ApiMeta:
    return ApiMeta(request_id=getattr(request.state, "request_id", None))


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    return HealthResponse(data=_base_payload(), meta=_meta(request))


@router.get("/health/ready", response_model=HealthResponse)
async def readiness_check(request: Request) -> HealthResponse:
    payload = _base_payload()
    payload["checks"] = {
        "database": "skipped",
        "redis": "skipped",
    }
    return HealthResponse(data=payload, meta=_meta(request))
