from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.application.bus.outbox_service import OutboxService
from app.common.api import ApiMeta
from app.infrastructure.bus.outbox_repository import OutboxRepository
from app.infrastructure.db import get_sessionmaker

router = APIRouter(prefix="/bus", tags=["bus"])


class TestEventRequest(BaseModel):
    topic: str = "system.test"
    payload: Dict[str, Any] = Field(default_factory=dict)


class OutboxMessageResponse(BaseModel):
    id: str
    message_type: str
    topic: str
    status: str


class OutboxMessageDataResponse(BaseModel):
    data: OutboxMessageResponse
    meta: Optional[ApiMeta] = None


def _meta(request: Request) -> ApiMeta:
    return ApiMeta(request_id=getattr(request.state, "request_id", None))


@router.post("/outbox/test", response_model=OutboxMessageDataResponse)
async def enqueue_test_event(
    payload: TestEventRequest,
    request: Request,
) -> OutboxMessageDataResponse:
    repository = OutboxRepository(get_sessionmaker())
    service = OutboxService(repository)
    message = await service.enqueue_event(payload.topic, payload.payload)

    return OutboxMessageDataResponse(
        data=OutboxMessageResponse(
            id=message.id,
            message_type=message.message_type,
            topic=message.topic,
            status=message.status,
        ),
        meta=_meta(request),
    )
