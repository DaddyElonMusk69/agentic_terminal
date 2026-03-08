import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.application.portfolio.dependencies import get_portfolio_service
from app.application.monitored_assets.dependencies import get_monitored_assets_service
from app.common.api import ApiErrorDetail, ApiErrorResponse, ApiMeta
from app.domain.portfolio.models import (
    ExchangeAccount,
    AccountState,
    Position,
    PortfolioSnapshot,
    DailyPnlSnapshot,
)
from app.infrastructure.exchange.ccxt_connector import is_retryable_exchange_error

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


class ExchangeAccountResponse(BaseModel):
    id: str
    name: str
    exchange: str
    is_active: bool
    is_testnet: bool
    created_at: datetime
    updated_at: datetime


class AccountStateResponse(BaseModel):
    account_value: float
    available_margin: float
    total_margin_used: float
    unrealized_pnl: float
    open_positions_count: int
    total_exposure_pct: float


class PositionResponse(BaseModel):
    symbol: str
    direction: str
    size: float
    entry_price: Optional[float]
    mark_price: Optional[float]
    unrealized_pnl: Optional[float]
    liquidation_price: Optional[float]
    margin: Optional[float]
    leverage: Optional[float]


class PortfolioSnapshotResponse(BaseModel):
    account: ExchangeAccountResponse
    state: AccountStateResponse
    positions: List[PositionResponse]


class PortfolioSnapshotDataResponse(BaseModel):
    data: PortfolioSnapshotResponse
    meta: Optional[ApiMeta] = None


class DailyPnlResponse(BaseModel):
    realized_pnl: float
    trade_count: int
    fills: List[Dict[str, Any]] = Field(default_factory=list)
    exchange: Optional[str] = None


class DailyPnlDataResponse(BaseModel):
    data: DailyPnlResponse
    meta: Optional[ApiMeta] = None


def _account_response(account: ExchangeAccount) -> ExchangeAccountResponse:
    return ExchangeAccountResponse(
        id=account.id,
        name=account.name,
        exchange=account.exchange,
        is_active=account.is_active,
        is_testnet=account.is_testnet,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


def _state_response(state: AccountState) -> AccountStateResponse:
    return AccountStateResponse(
        account_value=state.account_value,
        available_margin=state.available_margin,
        total_margin_used=state.total_margin_used,
        unrealized_pnl=state.unrealized_pnl,
        open_positions_count=state.open_positions_count,
        total_exposure_pct=state.total_exposure_pct,
    )


def _position_response(position: Position) -> PositionResponse:
    return PositionResponse(
        symbol=position.symbol,
        direction=position.direction,
        size=position.size,
        entry_price=position.entry_price,
        mark_price=position.mark_price,
        unrealized_pnl=position.unrealized_pnl,
        liquidation_price=position.liquidation_price,
        margin=position.margin,
        leverage=position.leverage,
    )


def _snapshot_response(snapshot: PortfolioSnapshot) -> PortfolioSnapshotResponse:
    return PortfolioSnapshotResponse(
        account=_account_response(snapshot.account),
        state=_state_response(snapshot.state),
        positions=[_position_response(p) for p in snapshot.positions],
    )


def _daily_pnl_response(snapshot: DailyPnlSnapshot) -> DailyPnlResponse:
    return DailyPnlResponse(
        realized_pnl=snapshot.realized_pnl,
        trade_count=snapshot.trade_count,
        fills=snapshot.fills,
        exchange=snapshot.exchange,
    )

def _meta(request: Request) -> ApiMeta:
    return ApiMeta(request_id=getattr(request.state, "request_id", None))


def _exchange_unavailable_response(request: Request) -> JSONResponse:
    payload = ApiErrorResponse(
        error=ApiErrorDetail(
            code="exchange_unavailable",
            message="Exchange temporarily unavailable. Please retry shortly.",
            details={"retryable": True},
        ),
        meta=_meta(request),
    )
    return JSONResponse(
        status_code=503,
        content=payload.model_dump(),
        headers={"Retry-After": "2"},
    )


@router.get("/snapshot", response_model=PortfolioSnapshotDataResponse)
async def get_portfolio_snapshot(request: Request) -> PortfolioSnapshotDataResponse | JSONResponse:
    service = get_portfolio_service()
    try:
        snapshot = await service.get_portfolio_snapshot()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        if is_retryable_exchange_error(exc):
            logger.warning(
                "Portfolio snapshot unavailable due to transient exchange error request_id=%s error=%s",
                getattr(request.state, "request_id", None),
                exc,
            )
            return _exchange_unavailable_response(request)
        raise
    try:
        assets_service = get_monitored_assets_service()
        await assets_service.sync_positions(snapshot.positions)
    except Exception:
        pass
    return PortfolioSnapshotDataResponse(
        data=_snapshot_response(snapshot),
        meta=_meta(request),
    )


@router.get("/daily-pnl", response_model=DailyPnlDataResponse)
async def get_daily_pnl(request: Request) -> DailyPnlDataResponse:
    service = get_portfolio_service()
    try:
        snapshot = await service.get_daily_pnl()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return DailyPnlDataResponse(
        data=_daily_pnl_response(snapshot),
        meta=_meta(request),
    )
