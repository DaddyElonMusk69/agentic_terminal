from app.domain.telegram.models import TelegramConfig, TelegramNotifications, TelegramRecipient
from app.infrastructure.repositories.telegram_repository import SqlTelegramConfigRepository


class TelegramConfigService:
    def __init__(self, repository: SqlTelegramConfigRepository) -> None:
        self._repository = repository

    async def get_config(self) -> TelegramConfig:
        config = await self._repository.get_config()
        if config is None:
            config = await self._repository.upsert(self._default_config())
        return config

    async def update_config(
        self,
        enabled: bool,
        chat_id: str,
        recipients: list[TelegramRecipient],
        notifications: TelegramNotifications,
        bot_token: str | None = None,
        update_bot_token: bool = False,
    ) -> TelegramConfig:
        current = await self.get_config()
        next_token = current.bot_token
        if update_bot_token:
            next_token = bot_token.strip() if bot_token and bot_token.strip() else None

        updated = TelegramConfig(
            enabled=enabled,
            bot_token=next_token,
            chat_id=chat_id.strip(),
            recipients=recipients,
            notifications=notifications,
            parse_mode=current.parse_mode,
            disable_notification=current.disable_notification,
        )
        return await self._repository.upsert(updated)

    def _default_config(self) -> TelegramConfig:
        return TelegramConfig(
            enabled=False,
            bot_token=None,
            chat_id="",
            recipients=[],
            notifications=TelegramNotifications(),
        )
