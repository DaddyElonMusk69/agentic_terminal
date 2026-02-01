from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.ai_providers.interfaces import ProviderConfigRepository
from app.domain.ai_providers.models import ProviderConfig
from app.infrastructure.crypto.cipher import PlaintextCipher, SecretCipher
from app.infrastructure.db.models.ai_provider import AgentProviderConfigModel


class SqlProviderConfigRepository(ProviderConfigRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], cipher: Optional[SecretCipher] = None) -> None:
        self._sessionmaker = sessionmaker
        self._cipher = cipher or PlaintextCipher()

    async def list_configs(self) -> List[ProviderConfig]:
        async with self._sessionmaker() as session:
            result = await session.execute(select(AgentProviderConfigModel))
            return [self._to_config(model) for model in result.scalars().all()]

    async def get_config(self, provider: str) -> Optional[ProviderConfig]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(AgentProviderConfigModel).where(AgentProviderConfigModel.provider == provider)
            )
            model = result.scalar_one_or_none()
            return self._to_config(model) if model else None

    async def upsert(self, config: ProviderConfig) -> ProviderConfig:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(AgentProviderConfigModel).where(AgentProviderConfigModel.provider == config.provider)
            )
            model = result.scalar_one_or_none()
            if model is None:
                model = AgentProviderConfigModel(provider=config.provider)
                session.add(model)

            model.api_key_encrypted = (
                self._cipher.encrypt(config.api_key) if config.api_key is not None else None
            )
            model.default_model = config.default_model
            model.is_enabled = config.is_enabled
            model.settings = config.settings or None

            await session.commit()
            await session.refresh(model)
            return self._to_config(model)

    async def delete(self, provider: str) -> None:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(AgentProviderConfigModel).where(AgentProviderConfigModel.provider == provider)
            )
            model = result.scalar_one_or_none()
            if model:
                await session.delete(model)
                await session.commit()

    def _to_config(self, model: AgentProviderConfigModel) -> ProviderConfig:
        api_key = None
        if model.api_key_encrypted:
            api_key = self._cipher.decrypt(model.api_key_encrypted)
        return ProviderConfig(
            provider=model.provider,
            api_key=api_key,
            default_model=model.default_model,
            is_enabled=model.is_enabled,
            settings=model.settings,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
