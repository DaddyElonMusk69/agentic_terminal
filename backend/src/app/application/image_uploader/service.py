from app.application.image_uploader.config_service import ImageUploaderConfigService
from app.infrastructure.external.image_uploader import build_image_uploader
from app.settings import Settings


class ImageUploaderService:
    def __init__(self, config_service: ImageUploaderConfigService, settings: Settings) -> None:
        self._config_service = config_service
        self._settings = settings

    async def get_uploader(self):
        config = await self._config_service.get_config()
        return build_image_uploader(self._settings, config)
