import asyncio
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.application.market_settings.dependencies import get_market_settings_service
from app.application.monitored_assets.dependencies import get_monitored_assets_service
from app.application.portfolio.dependencies import get_portfolio_service
from app.common.api import ApiMeta
from app.infrastructure.external.binance_client import BinanceClient


router = APIRouter(prefix="/market", tags=["market-settings"])


class AssetPayload(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)


class IntervalPayload(BaseModel):
    interval: str = Field(..., min_length=1, max_length=10)


class MonitoredAssetsResponse(BaseModel):
    data: List[str]
    meta: Optional[ApiMeta] = None


class MonitoredIntervalsResponse(BaseModel):
    data: List[str]
    meta: Optional[ApiMeta] = None


class PriceRequest(BaseModel):
    assets: Optional[List[str]] = None


class PriceQuote(BaseModel):
    symbol: str
    price: float
    change_percent: Optional[float] = None


class PriceQuotesResponse(BaseModel):
    data: List[PriceQuote]
    meta: Optional[ApiMeta] = None


class CandlePayload(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float


class CandleSeries(BaseModel):
    symbol: str
    interval: str
    candles: List[CandlePayload]


class CandleSeriesResponse(BaseModel):
    data: CandleSeries
    meta: Optional[ApiMeta] = None


def _meta(request: Request) -> ApiMeta:
    return ApiMeta(request_id=getattr(request.state, "request_id", None))


@router.get("/monitored-assets", response_model=MonitoredAssetsResponse)
async def list_assets(
    request: Request,
    include_positions: bool = True,
    force_refresh: bool = False,
) -> MonitoredAssetsResponse:
    assets_service = get_monitored_assets_service()
    assets = await assets_service.list_assets(
        include_positions=include_positions,
        force_refresh=force_refresh,
    )
    return MonitoredAssetsResponse(data=assets, meta=_meta(request))


@router.post("/monitored-assets", response_model=MonitoredAssetsResponse)
async def add_asset(payload: AssetPayload, request: Request) -> MonitoredAssetsResponse:
    service = get_market_settings_service()
    assets = await service.add_asset(payload.symbol)
    return MonitoredAssetsResponse(data=assets, meta=_meta(request))


@router.delete("/monitored-assets/{symbol}", response_model=MonitoredAssetsResponse)
async def remove_asset(symbol: str, request: Request) -> MonitoredAssetsResponse:
    service = get_market_settings_service()
    assets = await service.remove_asset(symbol)
    return MonitoredAssetsResponse(data=assets, meta=_meta(request))


@router.get("/monitored-intervals", response_model=MonitoredIntervalsResponse)
async def list_intervals(request: Request) -> MonitoredIntervalsResponse:
    service = get_market_settings_service()
    intervals = await service.list_intervals()
    return MonitoredIntervalsResponse(data=intervals, meta=_meta(request))


@router.post("/monitored-intervals", response_model=MonitoredIntervalsResponse)
async def add_interval(payload: IntervalPayload, request: Request) -> MonitoredIntervalsResponse:
    service = get_market_settings_service()
    intervals = await service.add_interval(payload.interval)
    return MonitoredIntervalsResponse(data=intervals, meta=_meta(request))


@router.delete("/monitored-intervals/{interval}", response_model=MonitoredIntervalsResponse)
async def remove_interval(interval: str, request: Request) -> MonitoredIntervalsResponse:
    service = get_market_settings_service()
    intervals = await service.remove_interval(interval)
    return MonitoredIntervalsResponse(data=intervals, meta=_meta(request))


@router.post("/prices", response_model=PriceQuotesResponse)
async def fetch_prices(payload: PriceRequest, request: Request) -> PriceQuotesResponse:
    monitored_service = get_monitored_assets_service()
    portfolio_service = get_portfolio_service()

    try:
        connector = await portfolio_service.get_active_connector()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    assets = payload.assets or await monitored_service.list_assets(
        include_positions=True,
    )
    assets = [asset.strip().upper() for asset in assets if asset and asset.strip()]

    quotes: List[PriceQuote] = []
    try:
        quote_map = await connector.fetch_ticker_quotes(assets)
    except Exception:
        quote_map = {}

    if not quote_map:
        for symbol in assets:
            try:
                quote = await connector.fetch_ticker_quote(symbol)
            except Exception:
                quote = None
            if quote is None:
                continue
            quotes.append(
                PriceQuote(
                    symbol=symbol,
                    price=quote.price,
                    change_percent=quote.change_percent,
                )
            )
    else:
        for symbol in assets:
            quote = quote_map.get(symbol)
            if quote is None:
                continue
            quotes.append(
                PriceQuote(
                    symbol=symbol,
                    price=quote.price,
                    change_percent=quote.change_percent,
                )
            )

    return PriceQuotesResponse(data=quotes, meta=_meta(request))


@router.get("/candles", response_model=CandleSeriesResponse)
async def fetch_candles(
    symbol: str,
    interval: str,
    request: Request,
    limit: int = 200,
) -> CandleSeriesResponse:
    symbol = (symbol or "").strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="Symbol is required")

    interval = (interval or "").strip().lower()
    if not interval:
        raise HTTPException(status_code=400, detail="Interval is required")

    try:
        limit_value = int(limit)
    except (TypeError, ValueError):
        limit_value = 200
    limit_value = max(1, min(limit_value, BinanceClient.MAX_KLINES_LIMIT))

    client = BinanceClient()
    candles = await asyncio.to_thread(
        client.fetch_candles,
        symbol,
        interval,
        limit_value,
    )
    payload = [
        CandlePayload(
            time=int(candle.timestamp_ms / 1000),
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
        )
        for candle in candles
    ]

    return CandleSeriesResponse(
        data=CandleSeries(symbol=symbol, interval=interval, candles=payload),
        meta=_meta(request),
    )
