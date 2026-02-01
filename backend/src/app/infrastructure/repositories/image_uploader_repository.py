from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.image_uploader.models import ImageUploaderConfig
from app.infrastructure.db.models.image_uploader import ImageUploaderConfigModel


class ImageUploaderConfigRepository:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get_config(self) -> Optional[ImageUploaderConfig]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(ImageUploaderConfigModel)
                .order_by(ImageUploaderConfigModel.id.desc())
                .limit(1)
            )
            model = result.scalars().first()
            if model is None:
                return None
            return ImageUploaderConfig(
                provider=model.provider,
                api_key=model.api_key,
                created_at=model.created_at,
                updated_at=model.updated_at,
            )

    async def upsert(self, config: ImageUploaderConfig) -> None:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(ImageUploaderConfigModel)
                .order_by(ImageUploaderConfigModel.id.desc())
                .limit(1)
            )
            model = result.scalars().first()
            if model is None:
                model = ImageUploaderConfigModel(
                    provider=config.provider,
                    api_key=config.api_key,
                )
                session.add(model)
            else:
                model.provider = config.provider
                model.api_key = config.api_key
            await session.commit()
