from functools import lru_cache

from app.application.ai_providers.service import AiProviderService
from app.infrastructure.crypto.cipher import get_credentials_cipher
from app.infrastructure.db import get_sessionmaker
from app.infrastructure.repositories.ai_provider_repository import SqlProviderConfigRepository
from app.settings import get_settings


@lru_cache(maxsize=1)
def get_ai_provider_service() -> AiProviderService:
    settings = get_settings()
    repository = SqlProviderConfigRepository(get_sessionmaker(), cipher=get_credentials_cipher())
    return AiProviderService(
        repository,
        codex_cli_path=settings.codex_cli_path,
        codex_cli_timeout_seconds=settings.codex_cli_timeout_seconds,
    )
