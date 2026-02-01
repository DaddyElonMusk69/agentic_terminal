from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.dynamic_assets.models import DynamicAssetsConfig
from app.domain.dynamic_assets.interfaces import DynamicAssetsConfigRepository
from app.infrastructure.crypto.cipher import PlaintextCipher, SecretCipher
from app.infrastructure.db.models.dynamic_assets import DynamicAssetConfigModel


class SqlDynamicAssetsConfigRepository(DynamicAssetsConfigRepository):
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        cipher: Optional[SecretCipher] = None,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._cipher = cipher or PlaintextCipher()

    async def get_config(self) -> Optional[DynamicAssetsConfig]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(DynamicAssetConfigModel)
                .order_by(DynamicAssetConfigModel.id.desc())
                .limit(1)
            )
            model = result.scalars().first()
            if model is None:
                return None
            return self._to_config(model)

    async def upsert(self, config: DynamicAssetsConfig) -> DynamicAssetsConfig:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(DynamicAssetConfigModel)
                .order_by(DynamicAssetConfigModel.id.desc())
                .limit(1)
            )
            model = result.scalars().first()
            if model is None:
                model = DynamicAssetConfigModel()
                session.add(model)

            model.enabled = config.enabled
            model.api_key_encrypted = (
                self._cipher.encrypt(config.api_key) if config.api_key is not None else None
            )
            model.sources = config.sources or None
            model.refresh_interval_seconds = config.refresh_interval_seconds
            model.last_fetch_at = config.last_fetch_at
            model.last_success_at = config.last_success_at
            model.last_success_assets = config.last_success_assets or None

            await session.commit()
            await session.refresh(model)
            return self._to_config(model)

    def _to_config(self, model: DynamicAssetConfigModel) -> DynamicAssetsConfig:
        api_key = None
        if model.api_key_encrypted:
            api_key = self._cipher.decrypt(model.api_key_encrypted)
        return DynamicAssetsConfig(
            enabled=model.enabled,
            api_key=api_key,
            sources=model.sources or {},
            refresh_interval_seconds=model.refresh_interval_seconds,
            last_fetch_at=model.last_fetch_at,
            last_success_at=model.last_success_at,
            last_success_assets=model.last_success_assets,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
