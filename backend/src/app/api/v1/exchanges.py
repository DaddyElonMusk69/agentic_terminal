from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.application.bus.outbox_service import OutboxService
from app.application.portfolio.dependencies import get_portfolio_service
from app.common.api import ApiMeta
from app.domain.portfolio.models import ExchangeAccount, ExchangeCredentials
from app.infrastructure.bus.outbox_repository import OutboxRepository
from app.infrastructure.db import get_sessionmaker

router = APIRouter(prefix="/portfolio/exchanges", tags=["portfolio-exchange"])


class ExchangeCredentialsPayload(BaseModel):
    api_key: str = Field(..., min_length=1)
    api_secret: str = Field(..., min_length=1)
    passphrase: Optional[str] = None
    agent_key: Optional[str] = None


class ExchangeAccountCreate(BaseModel):
    name: str = Field(..., min_length=1)
    exchange: str = Field(..., min_length=1)
    is_testnet: bool = False
    wallet_address: Optional[str] = None
    credentials: ExchangeCredentialsPayload


class ExchangeAccountUpdate(BaseModel):
    name: Optional[str] = None
    is_testnet: Optional[bool] = None
    wallet_address: Optional[str] = None


class ExchangeCredentialStatus(BaseModel):
    api_key: bool
    api_secret: bool
    passphrase: bool
    agent_key: bool


class ExchangeValidationStatus(BaseModel):
    status: str
    last_validated_at: Optional[datetime] = None
    error: Optional[str] = None


class ExchangeAccountResponse(BaseModel):
    id: str
    name: str
    exchange: str
    is_active: bool
    is_testnet: bool
    wallet_address: Optional[str] = None
    credentials: ExchangeCredentialStatus
    validation: ExchangeValidationStatus
    created_at: datetime
    updated_at: datetime


class ExchangeAccountListResponse(BaseModel):
    data: List[ExchangeAccountResponse]
    meta: Optional[ApiMeta] = None


class ExchangeAccountDataResponse(BaseModel):
    data: ExchangeAccountResponse
    meta: Optional[ApiMeta] = None


class ActionResponse(BaseModel):
    data: dict
    meta: Optional[ApiMeta] = None


def _outbox_service() -> OutboxService:
    return OutboxService(OutboxRepository(get_sessionmaker()))


def _meta(request: Request) -> ApiMeta:
    return ApiMeta(request_id=getattr(request.state, "request_id", None))


def _credential_status(credentials: Optional[ExchangeCredentials]) -> ExchangeCredentialStatus:
    return ExchangeCredentialStatus(
        api_key=bool(credentials and credentials.api_key),
        api_secret=bool(credentials and credentials.api_secret),
        passphrase=bool(credentials and credentials.passphrase),
        agent_key=bool(credentials and credentials.agent_key),
    )


def _validation_status(account: ExchangeAccount) -> ExchangeValidationStatus:
    return ExchangeValidationStatus(
        status=account.validation_status,
        last_validated_at=account.last_validated_at,
        error=account.validation_error,
    )


async def _to_response(account: ExchangeAccount) -> ExchangeAccountResponse:
    service = get_portfolio_service()
    credentials = await service.get_credentials(account.id)
    return ExchangeAccountResponse(
        id=account.id,
        name=account.name,
        exchange=account.exchange,
        is_active=account.is_active,
        is_testnet=account.is_testnet,
        wallet_address=account.wallet_address,
        credentials=_credential_status(credentials),
        validation=_validation_status(account),
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


@router.get("/active", response_model=ExchangeAccountDataResponse)
async def get_active_account(request: Request) -> ExchangeAccountDataResponse:
    service = get_portfolio_service()
    account = await service.get_active_account()
    if not account:
        raise HTTPException(status_code=404, detail="No active account")
    return ExchangeAccountDataResponse(
        data=await _to_response(account),
        meta=_meta(request),
    )


@router.post("/deactivate", response_model=ActionResponse)
async def deactivate_account(request: Request) -> ActionResponse:
    service = get_portfolio_service()
    await service.deactivate_account()
    await _outbox_service().enqueue_event("portfolio.exchange.deactivated", {"deactivated": True})
    return ActionResponse(data={"deactivated": True}, meta=_meta(request))


@router.get("", response_model=ExchangeAccountListResponse)
async def list_accounts(request: Request) -> ExchangeAccountListResponse:
    service = get_portfolio_service()
    accounts = await service.list_accounts()
    payload = [await _to_response(account) for account in accounts]
    return ExchangeAccountListResponse(data=payload, meta=_meta(request))


@router.post("", response_model=ExchangeAccountDataResponse)
async def create_account(
    payload: ExchangeAccountCreate,
    request: Request,
) -> ExchangeAccountDataResponse:
    service = get_portfolio_service()
    account = await service.create_account(
        name=payload.name,
        exchange=payload.exchange,
        api_key=payload.credentials.api_key,
        api_secret=payload.credentials.api_secret,
        passphrase=payload.credentials.passphrase,
        is_testnet=payload.is_testnet,
        wallet_address=payload.wallet_address,
        agent_key=payload.credentials.agent_key,
    )
    response = await _to_response(account)
    await _outbox_service().enqueue_event("portfolio.exchange.created", response.model_dump())
    return ExchangeAccountDataResponse(data=response, meta=_meta(request))


@router.get("/{account_id}", response_model=ExchangeAccountDataResponse)
async def get_account(account_id: str, request: Request) -> ExchangeAccountDataResponse:
    service = get_portfolio_service()
    account = await service.get_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return ExchangeAccountDataResponse(data=await _to_response(account), meta=_meta(request))


@router.patch("/{account_id}", response_model=ExchangeAccountDataResponse)
async def update_account(
    account_id: str,
    payload: ExchangeAccountUpdate,
    request: Request,
) -> ExchangeAccountDataResponse:
    service = get_portfolio_service()
    try:
        account = await service.update_account(
            account_id,
            name=payload.name,
            is_testnet=payload.is_testnet,
            wallet_address=payload.wallet_address,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Account not found")
    response = await _to_response(account)
    await _outbox_service().enqueue_event("portfolio.exchange.updated", response.model_dump())
    return ExchangeAccountDataResponse(data=response, meta=_meta(request))


@router.delete("/{account_id}", response_model=ActionResponse)
async def delete_account(account_id: str, request: Request) -> ActionResponse:
    service = get_portfolio_service()
    account = await service.get_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    await service.delete_account(account_id)
    await _outbox_service().enqueue_event(
        "portfolio.exchange.deleted",
        {"account_id": account_id, "exchange": account.exchange},
    )
    return ActionResponse(data={"deleted": True}, meta=_meta(request))


@router.post("/{account_id}/activate", response_model=ExchangeAccountDataResponse)
async def activate_account(
    account_id: str,
    request: Request,
) -> ExchangeAccountDataResponse:
    service = get_portfolio_service()
    try:
        account = await service.activate_account(account_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Account not found")
    response = await _to_response(account)
    await _outbox_service().enqueue_event("portfolio.exchange.activated", response.model_dump())
    return ExchangeAccountDataResponse(data=response, meta=_meta(request))


@router.post("/{account_id}/validate", response_model=ExchangeAccountDataResponse)
async def validate_account(
    account_id: str,
    request: Request,
) -> ExchangeAccountDataResponse:
    service = get_portfolio_service()
    try:
        account = await service.validate_account(account_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    response = await _to_response(account)
    await _outbox_service().enqueue_event("portfolio.exchange.validated", response.model_dump())
    return ExchangeAccountDataResponse(data=response, meta=_meta(request))
