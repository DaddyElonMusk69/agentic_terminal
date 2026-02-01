from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.telegram.models import (
    TelegramConfig,
    TelegramNotifications,
    TelegramRecipient,
)
from app.infrastructure.crypto.cipher import PlaintextCipher, SecretCipher
from app.infrastructure.db.models.telegram import TelegramConfigModel


class SqlTelegramConfigRepository:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        cipher: Optional[SecretCipher] = None,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._cipher = cipher or PlaintextCipher()

    async def get_config(self) -> Optional[TelegramConfig]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(TelegramConfigModel)
                .order_by(TelegramConfigModel.id.desc())
                .limit(1)
            )
            model = result.scalars().first()
            if model is None:
                return None
            return self._to_config(model)

    async def upsert(self, config: TelegramConfig) -> TelegramConfig:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(TelegramConfigModel)
                .order_by(TelegramConfigModel.id.desc())
                .limit(1)
            )
            model = result.scalars().first()
            if model is None:
                model = TelegramConfigModel()
                session.add(model)

            model.enabled = config.enabled
            model.bot_token_encrypted = (
                self._cipher.encrypt(config.bot_token)
                if config.bot_token
                else None
            )
            model.chat_id = config.chat_id or None
            model.recipients = [recipient.to_dict() for recipient in config.recipients] or None
            model.notifications = config.notifications.to_dict() if config.notifications else None
            model.parse_mode = config.parse_mode
            model.disable_notification = config.disable_notification

            await session.commit()
            await session.refresh(model)
            return self._to_config(model)

    def _to_config(self, model: TelegramConfigModel) -> TelegramConfig:
        bot_token = None
        if model.bot_token_encrypted:
            bot_token = self._cipher.decrypt(model.bot_token_encrypted)

        recipients_raw = model.recipients or []
        recipients = [
            TelegramRecipient.from_dict(item)
            for item in recipients_raw
            if isinstance(item, dict)
        ]

        notifications = TelegramNotifications.from_dict(model.notifications or {})

        return TelegramConfig(
            enabled=model.enabled,
            bot_token=bot_token,
            chat_id=model.chat_id or "",
            recipients=recipients,
            notifications=notifications,
            parse_mode=model.parse_mode or "Markdown",
            disable_notification=bool(model.disable_notification),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
