from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Type

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.api import ApiMeta
from app.infrastructure.db import get_session
from app.infrastructure.db.models.llm_queue import LlmQueueRequestModel
from app.infrastructure.db.models.order_queue import OrderQueueRequestModel
from app.infrastructure.db.models.prompt_build_queue import PromptBuildRequestModel

router = APIRouter(prefix="/observability", tags=["observability"])


class QueueMetric(BaseModel):
    key: str
    name: str
    depth: int
    in_flight: int
    dlq: int
    age_oldest_ms: Optional[int] = None
    throughput_per_min: int
    p95_latency_ms: Optional[float] = None


class QueueMetricsPayload(BaseModel):
    queues: List[QueueMetric]


class QueueMetricsResponse(BaseModel):
    data: QueueMetricsPayload
    meta: Optional[ApiMeta] = None


def _meta(request: Request) -> ApiMeta:
    return ApiMeta(request_id=getattr(request.state, "request_id", None))


def _percentile(values: List[float], percentile: float) -> Optional[float]:
    if not values:
        return None
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = max(0, min(len(sorted_values) - 1, int(round((percentile / 100) * (len(sorted_values) - 1)))))
    return sorted_values[rank]


async def _queue_metric(
    session: AsyncSession,
    model: Type,
    key: str,
    name: str,
    now: datetime,
) -> QueueMetric:
    queued_count = await session.scalar(
        select(func.count()).select_from(model).where(model.status == "queued")
    )
    in_flight_count = await session.scalar(
        select(func.count()).select_from(model).where(model.status == "in_progress")
    )
    oldest_created_at = await session.scalar(
        select(func.min(model.created_at)).where(model.status == "queued")
    )

    throughput_window = now - timedelta(minutes=1)
    throughput_count = await session.scalar(
        select(func.count())
        .select_from(model)
        .where(model.completed_at.is_not(None))
        .where(model.completed_at >= throughput_window)
    )

    dlq_window = now - timedelta(minutes=60)
    dlq_count = await session.scalar(
        select(func.count())
        .select_from(model)
        .where(model.status.in_(["failed", "dropped"]))
        .where(model.completed_at.is_not(None))
        .where(model.completed_at >= dlq_window)
    )

    latency_window = now - timedelta(minutes=60)
    latency_rows = await session.execute(
        select(model.created_at, model.started_at, model.completed_at)
        .where(model.completed_at.is_not(None))
        .where(model.completed_at >= latency_window)
        .order_by(model.completed_at.desc())
        .limit(200)
    )

    latencies: List[float] = []
    for created_at, started_at, completed_at in latency_rows.all():
        if completed_at is None:
            continue
        anchor = started_at or created_at
        if anchor is None:
            continue
        duration_ms = (completed_at - anchor).total_seconds() * 1000
        if duration_ms >= 0:
            latencies.append(duration_ms)

    age_oldest_ms: Optional[int] = None
    if oldest_created_at is not None:
        age_oldest_ms = int((now - oldest_created_at).total_seconds() * 1000)

    return QueueMetric(
        key=key,
        name=name,
        depth=int(queued_count or 0),
        in_flight=int(in_flight_count or 0),
        dlq=int(dlq_count or 0),
        age_oldest_ms=age_oldest_ms,
        throughput_per_min=int(throughput_count or 0),
        p95_latency_ms=_percentile(latencies, 95.0),
    )


@router.get("/queues", response_model=QueueMetricsResponse)
async def get_queue_metrics(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> QueueMetricsResponse:
    now = datetime.now(timezone.utc)
    queues = [
        await _queue_metric(session, PromptBuildRequestModel, "prompt", "Prompt Queue", now),
        await _queue_metric(session, LlmQueueRequestModel, "llm", "LLM Queue", now),
        await _queue_metric(session, OrderQueueRequestModel, "order", "Order Queue", now),
    ]
    return QueueMetricsResponse(data=QueueMetricsPayload(queues=queues), meta=_meta(request))
