from functools import lru_cache
from app.application.image_uploader.dependencies import get_image_uploader_config_service
from app.application.image_uploader.service import ImageUploaderService
from app.application.prompt_builder.service import PromptBuilderService
from app.application.quant_scanner.dependencies import get_quant_scanner_service
from app.application.chart_preview.dependencies import get_chart_preview_service
from app.application.portfolio.dependencies import get_portfolio_service
from app.application.risk_management.dependencies import get_risk_management_config_service
from app.infrastructure.db import get_sessionmaker
from app.infrastructure.external.codex_temp_images import CodexTempImageStore
from app.infrastructure.repositories.prompt_template_repository import SqlPromptTemplateRepository
from app.settings import get_settings


@lru_cache(maxsize=1)
def get_prompt_builder_service() -> PromptBuilderService:
    settings = get_settings()
    uploader_service = ImageUploaderService(get_image_uploader_config_service(), settings)
    template_repo = SqlPromptTemplateRepository(get_sessionmaker())
    quant_service = get_quant_scanner_service()
    chart_preview_service = get_chart_preview_service()
    portfolio_service = get_portfolio_service()
    risk_config_service = get_risk_management_config_service()
    codex_temp_images = CodexTempImageStore(settings.codex_temp_image_path)

    return PromptBuilderService(
        template_repository=template_repo,
        quant_provider=quant_service,
        chart_preview_service=chart_preview_service,
        uploader_service=uploader_service,
        portfolio_service=portfolio_service,
        risk_config_service=risk_config_service,
        codex_temp_images=codex_temp_images,
        upload_concurrency=settings.prompt_image_upload_concurrency,
    )
