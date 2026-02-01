from app.domain.image_uploader.models import ImageUploaderConfig
from app.infrastructure.repositories.image_uploader_repository import ImageUploaderConfigRepository


class ImageUploaderConfigService:
    def __init__(self, repository: ImageUploaderConfigRepository) -> None:
        self._repository = repository

    async def get_config(self) -> ImageUploaderConfig | None:
        return await self._repository.get_config()

    async def set_config(self, provider: str, api_key: str | None) -> None:
        config = ImageUploaderConfig(provider=provider, api_key=api_key)
        await self._repository.upsert(config)
