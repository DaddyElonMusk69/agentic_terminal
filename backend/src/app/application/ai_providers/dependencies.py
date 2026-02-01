from functools import lru_cache

from app.application.ai_providers.service import AiProviderService
from app.infrastructure.crypto.cipher import get_credentials_cipher
from app.infrastructure.db import get_sessionmaker
from app.infrastructure.repositories.ai_provider_repository import SqlProviderConfigRepository


@lru_cache(maxsize=1)
def get_ai_provider_service() -> AiProviderService:
    repository = SqlProviderConfigRepository(get_sessionmaker(), cipher=get_credentials_cipher())
    return AiProviderService(repository)
