from dataclasses import dataclass
from typing import Optional

from app.application.telegram.config_service import TelegramConfigService
from app.infrastructure.external.telegram_client import TelegramClient


@dataclass(frozen=True)
class TelegramSendResult:
    sent: bool
    error: Optional[str] = None
    attempted: int = 0
    delivered: int = 0


class TelegramMessageService:
    def __init__(
        self,
        config_service: TelegramConfigService,
        client: Optional[TelegramClient] = None,
    ) -> None:
        self._config_service = config_service
        self._client = client or TelegramClient()

    async def send_message(
        self,
        text: str,
        chat_id: Optional[str] = None,
        bot_token: Optional[str] = None,
        parse_mode: Optional[str] = None,
        disable_notification: Optional[bool] = None,
        respect_enabled: bool = True,
    ) -> TelegramSendResult:
        config = await self._config_service.get_config()
        token = bot_token or config.bot_token
        if not token:
            return TelegramSendResult(sent=False, error="Bot token not configured")

        if respect_enabled and not config.enabled:
            return TelegramSendResult(sent=False, error="Telegram notifications are disabled")

        recipients = [chat_id] if chat_id else config.get_enabled_chat_ids()
        if not recipients:
            return TelegramSendResult(sent=False, error="No recipients configured")

        mode = parse_mode if parse_mode is not None else config.parse_mode
        silent = disable_notification if disable_notification is not None else config.disable_notification

        delivered = 0
        errors = []
        for target in recipients:
            if not target:
                continue
            success = await self._client.send_message(
                bot_token=token,
                chat_id=target,
                text=text,
                parse_mode=mode,
                disable_notification=silent,
            )
            if success:
                delivered += 1
            else:
                errors.append(self._client.last_error or "Failed to send")

        if delivered > 0:
            return TelegramSendResult(sent=True, attempted=len(recipients), delivered=delivered)

        error = "; ".join(errors) if errors else "Failed to send"
        return TelegramSendResult(sent=False, error=error, attempted=len(recipients), delivered=0)
