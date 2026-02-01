from typing import List, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.application.image_uploader.dependencies import get_image_uploader_config_service
from app.common.api import ApiMeta
from app.common.errors import AppError
from app.domain.image_uploader.models import ImageUploaderConfig


router = APIRouter(prefix="/integrations", tags=["integrations"])

SUPPORTED_PROVIDERS = ["filesystem", "imgbb", "freeimage"]


class ImageUploaderConfigView(BaseModel):
    provider: str
    api_key_present: bool
    supported_providers: List[str]


class ImageUploaderConfigResponse(BaseModel):
    data: ImageUploaderConfigView
    meta: Optional[ApiMeta] = None


class ImageUploaderUpdatePayload(BaseModel):
    provider: str = Field(..., min_length=1)
    api_key: Optional[str] = None


def _meta(request: Request) -> ApiMeta:
    return ApiMeta(request_id=getattr(request.state, "request_id", None))


def _normalize_provider(value: str) -> str:
    provider = value.strip().lower()
    if provider == "freeimage.host":
        provider = "freeimage"
    return provider


def _requires_key(provider: str) -> bool:
    return provider in ("imgbb", "freeimage")


@router.get("/image-uploader", response_model=ImageUploaderConfigResponse)
async def get_image_uploader_config(request: Request) -> ImageUploaderConfigResponse:
    service = get_image_uploader_config_service()
    config = await service.get_config()
    provider = _normalize_provider(config.provider) if config else "filesystem"
    api_key_present = bool(config.api_key) if config else False
    view = ImageUploaderConfigView(
        provider=provider,
        api_key_present=api_key_present,
        supported_providers=SUPPORTED_PROVIDERS,
    )
    return ImageUploaderConfigResponse(data=view, meta=_meta(request))


@router.put("/image-uploader", response_model=ImageUploaderConfigResponse)
async def update_image_uploader_config(
    payload: ImageUploaderUpdatePayload,
    request: Request,
) -> ImageUploaderConfigResponse:
    provider = _normalize_provider(payload.provider)
    if provider not in SUPPORTED_PROVIDERS:
        raise AppError(
            code="invalid_image_uploader",
            message=f"provider must be one of: {', '.join(SUPPORTED_PROVIDERS)}",
        )

    service = get_image_uploader_config_service()
    current = await service.get_config()
    api_key = payload.api_key.strip() if payload.api_key else None

    if provider == "filesystem":
        api_key = None
    elif api_key is None and current and _normalize_provider(current.provider) == provider:
        api_key = current.api_key

    if _requires_key(provider) and not api_key:
        raise AppError(
            code="image_uploader_api_key_required",
            message="API key is required for the selected image host.",
        )

    await service.set_config(provider=provider, api_key=api_key)

    view = ImageUploaderConfigView(
        provider=provider,
        api_key_present=bool(api_key),
        supported_providers=SUPPORTED_PROVIDERS,
    )
    return ImageUploaderConfigResponse(data=view, meta=_meta(request))
