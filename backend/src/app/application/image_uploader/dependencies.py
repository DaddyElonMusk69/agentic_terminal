from functools import lru_cache

from app.application.image_uploader.config_service import ImageUploaderConfigService
from app.infrastructure.db import get_sessionmaker
from app.infrastructure.repositories.image_uploader_repository import ImageUploaderConfigRepository


@lru_cache(maxsize=1)
def get_image_uploader_config_service() -> ImageUploaderConfigService:
    repository = ImageUploaderConfigRepository(get_sessionmaker())
    return ImageUploaderConfigService(repository)
