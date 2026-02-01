from typing import Dict, List, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.application.telegram.dependencies import (
    get_telegram_config_service,
    get_telegram_message_service,
)
from app.common.api import ApiMeta
from app.common.errors import AppError
from app.domain.telegram.models import TelegramNotifications, TelegramRecipient


router = APIRouter(prefix="/integrations", tags=["integrations"])

SUPPORTED_LANGUAGES: Dict[str, str] = {
    "en": "English",
    "zh-CN": "Chinese (Simplified)",
    "zh-TW": "Chinese (Traditional)",
    "ja": "Japanese",
    "ko": "Korean",
    "es": "Spanish",
    "ru": "Russian",
}


class TelegramRecipientView(BaseModel):
    chat_id: str
    name: str = ""
    enabled: bool = True
    language: str = "en"


class TelegramNotificationsView(BaseModel):
    signal_open: bool = True
    signal_change: bool = True
    signal_close: bool = False
    llm_considerations: bool = False
    ema_automation: bool = True


class TelegramConfigView(BaseModel):
    enabled: bool
    bot_token_set: bool
    chat_id: str
    recipients: List[TelegramRecipientView]
    notifications: TelegramNotificationsView
    supported_languages: Dict[str, str]


class TelegramConfigResponse(BaseModel):
    data: TelegramConfigView
    meta: Optional[ApiMeta] = None


class TelegramRecipientPayload(BaseModel):
    chat_id: str = Field(..., min_length=1)
    name: str = ""
    enabled: bool = True
    language: str = "en"


class TelegramNotificationsPayload(BaseModel):
    signal_open: bool = True
    signal_change: bool = True
    signal_close: bool = False
    llm_considerations: bool = False
    ema_automation: bool = True


class TelegramConfigUpdatePayload(BaseModel):
    enabled: bool
    chat_id: Optional[str] = ""
    recipients: List[TelegramRecipientPayload] = Field(default_factory=list)
    notifications: TelegramNotificationsPayload = Field(default_factory=TelegramNotificationsPayload)
    bot_token: Optional[str] = None


class TelegramTestPayload(BaseModel):
    bot_token: Optional[str] = None
    chat_id: Optional[str] = None
    send_test_message: bool = True


class TelegramTestResult(BaseModel):
    sent: bool
    error: Optional[str] = None


class TelegramTestResponse(BaseModel):
    data: TelegramTestResult
    meta: Optional[ApiMeta] = None


def _meta(request: Request) -> ApiMeta:
    return ApiMeta(request_id=getattr(request.state, "request_id", None))


def _to_view(config) -> TelegramConfigView:
    return TelegramConfigView(
        enabled=config.enabled,
        bot_token_set=bool(config.bot_token),
        chat_id=config.chat_id,
        recipients=[TelegramRecipientView(**recipient.to_dict()) for recipient in config.recipients],
        notifications=TelegramNotificationsView(**config.notifications.to_dict()),
        supported_languages=SUPPORTED_LANGUAGES,
    )


@router.get("/telegram", response_model=TelegramConfigResponse)
async def get_telegram_config(request: Request) -> TelegramConfigResponse:
    service = get_telegram_config_service()
    config = await service.get_config()
    return TelegramConfigResponse(data=_to_view(config), meta=_meta(request))


@router.put("/telegram", response_model=TelegramConfigResponse)
async def update_telegram_config(
    payload: TelegramConfigUpdatePayload,
    request: Request,
) -> TelegramConfigResponse:
    service = get_telegram_config_service()

    recipients = [TelegramRecipient.from_dict(item.model_dump()) for item in payload.recipients]
    notifications = TelegramNotifications.from_dict(payload.notifications.model_dump())
    update_bot_token = "bot_token" in payload.model_fields_set

    config = await service.update_config(
        enabled=payload.enabled,
        chat_id=payload.chat_id or "",
        recipients=recipients,
        notifications=notifications,
        bot_token=payload.bot_token,
        update_bot_token=update_bot_token,
    )
    return TelegramConfigResponse(data=_to_view(config), meta=_meta(request))


@router.post("/telegram/test", response_model=TelegramTestResponse)
async def test_telegram_connection(
    payload: TelegramTestPayload,
    request: Request,
) -> TelegramTestResponse:
    message_service = get_telegram_message_service()
    chat_id = payload.chat_id

    if not payload.send_test_message:
        raise AppError(
            code="telegram_test_requires_message",
            message="send_test_message must be true to run a test.",
        )

    result = await message_service.send_message(
        "Telegram integration is working correctly.",
        chat_id=chat_id,
        bot_token=payload.bot_token,
        parse_mode=None,
        respect_enabled=False,
    )
    if not result.sent:
        raise AppError(code="telegram_test_failed", message=result.error or "Test failed.")

    view = TelegramTestResult(sent=True, error=None)
    return TelegramTestResponse(data=view, meta=_meta(request))
