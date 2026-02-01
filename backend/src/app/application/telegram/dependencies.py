from functools import lru_cache

from app.application.telegram.config_service import TelegramConfigService
from app.application.telegram.message_service import TelegramMessageService
from app.application.telegram.notifications_service import TelegramNotificationService
from app.infrastructure.crypto.cipher import get_credentials_cipher
from app.infrastructure.db import get_sessionmaker
from app.infrastructure.repositories.telegram_repository import SqlTelegramConfigRepository


@lru_cache(maxsize=1)
def get_telegram_config_service() -> TelegramConfigService:
    repository = SqlTelegramConfigRepository(
        get_sessionmaker(),
        cipher=get_credentials_cipher(),
    )
    return TelegramConfigService(repository)


@lru_cache(maxsize=1)
def get_telegram_message_service() -> TelegramMessageService:
    return TelegramMessageService(get_telegram_config_service())


@lru_cache(maxsize=1)
def get_telegram_notification_service() -> TelegramNotificationService:
    return TelegramNotificationService(
        config_service=get_telegram_config_service(),
        message_service=get_telegram_message_service(),
    )
