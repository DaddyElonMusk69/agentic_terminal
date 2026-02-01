from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.application.ai_providers.dependencies import get_ai_provider_service
from app.common.api import ApiMeta


router = APIRouter(prefix="/ai/providers", tags=["ai-providers"])


class ProviderSettingsResponse(BaseModel):
    base_url: Optional[str] = None
    display_name: Optional[str] = None
    protocol: Optional[str] = None


class ProviderInfoResponse(BaseModel):
    name: str
    models: List[str] = Field(default_factory=list)
    configured: bool
    is_enabled: bool
    default_model: Optional[str] = None
    settings: Optional[ProviderSettingsResponse] = None


class ProviderListResponse(BaseModel):
    data: List[ProviderInfoResponse]
    meta: Optional[ApiMeta] = None


class ProviderUpsertRequest(BaseModel):
    provider: str = Field(..., min_length=1, max_length=50)
    api_key: Optional[str] = None
    default_model: Optional[str] = None
    is_enabled: Optional[bool] = None
    base_url: Optional[str] = None
    display_name: Optional[str] = None
    protocol: Optional[str] = None


class ProviderDataResponse(BaseModel):
    data: ProviderInfoResponse
    meta: Optional[ApiMeta] = None


class ProviderModelsResponse(BaseModel):
    provider: str
    models: List[str]


class ProviderModelsDataResponse(BaseModel):
    data: ProviderModelsResponse
    meta: Optional[ApiMeta] = None


class ProviderValidationRequest(BaseModel):
    api_key: Optional[str] = None
    model: Optional[str] = None


class ProviderValidationResponse(BaseModel):
    provider: str
    model: str
    latency_ms: float
    valid: bool


class ProviderValidationDataResponse(BaseModel):
    data: ProviderValidationResponse
    meta: Optional[ApiMeta] = None


class ProviderDeleteResponse(BaseModel):
    data: dict
    meta: Optional[ApiMeta] = None


def _meta(request: Request) -> ApiMeta:
    return ApiMeta(request_id=getattr(request.state, "request_id", None))


def _to_settings(settings: Optional[dict]) -> Optional[ProviderSettingsResponse]:
    if not settings:
        return None
    return ProviderSettingsResponse(
        base_url=settings.get("base_url"),
        display_name=settings.get("display_name"),
        protocol=settings.get("protocol"),
    )


def _to_provider_response(provider) -> ProviderInfoResponse:
    return ProviderInfoResponse(
        name=provider.name,
        models=provider.models,
        configured=provider.configured,
        is_enabled=provider.is_enabled,
        default_model=provider.default_model,
        settings=_to_settings(provider.settings),
    )


@router.get("", response_model=ProviderListResponse)
async def list_providers(request: Request) -> ProviderListResponse:
    service = get_ai_provider_service()
    providers = await service.list_providers()
    payload = [_to_provider_response(provider) for provider in providers]
    return ProviderListResponse(data=payload, meta=_meta(request))


@router.post("", response_model=ProviderDataResponse)
async def upsert_provider(payload: ProviderUpsertRequest, request: Request) -> ProviderDataResponse:
    service = get_ai_provider_service()
    try:
        provider = await service.upsert_provider(
            provider=payload.provider,
            api_key=payload.api_key,
            api_key_provided="api_key" in payload.model_fields_set,
            default_model=payload.default_model,
            default_model_provided="default_model" in payload.model_fields_set,
            is_enabled=payload.is_enabled,
            is_enabled_provided="is_enabled" in payload.model_fields_set,
            base_url=payload.base_url,
            base_url_provided="base_url" in payload.model_fields_set,
            display_name=payload.display_name,
            display_name_provided="display_name" in payload.model_fields_set,
            protocol=payload.protocol,
            protocol_provided="protocol" in payload.model_fields_set,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return ProviderDataResponse(data=_to_provider_response(provider), meta=_meta(request))


@router.delete("/{provider}", response_model=ProviderDeleteResponse)
async def delete_provider(provider: str, request: Request) -> ProviderDeleteResponse:
    service = get_ai_provider_service()
    try:
        await service.delete_provider(provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ProviderDeleteResponse(data={"deleted": True}, meta=_meta(request))


@router.get("/{provider}/models", response_model=ProviderModelsDataResponse)
async def list_models(provider: str, request: Request) -> ProviderModelsDataResponse:
    service = get_ai_provider_service()
    try:
        models = await service.list_models(provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    payload = ProviderModelsResponse(provider=provider, models=models)
    return ProviderModelsDataResponse(data=payload, meta=_meta(request))


@router.post("/{provider}/validate", response_model=ProviderValidationDataResponse)
async def validate_provider(
    provider: str,
    payload: ProviderValidationRequest,
    request: Request,
) -> ProviderValidationDataResponse:
    service = get_ai_provider_service()
    try:
        result = await service.validate_provider(
            provider=provider,
            api_key=payload.api_key,
            api_key_provided="api_key" in payload.model_fields_set,
            model=payload.model,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return ProviderValidationDataResponse(
        data=ProviderValidationResponse(
            provider=result.provider,
            model=result.model,
            latency_ms=result.latency_ms,
            valid=result.valid,
        ),
        meta=_meta(request),
    )
