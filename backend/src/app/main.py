from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.application.auto_add.runtime import get_auto_add_runtime
from app.application.pending_entry.runtime import get_pending_entry_runtime
from app.application.protection_reconciler.runtime import get_protection_reconciler_runtime
from app.api.infra import register_exception_handlers, register_request_id
from app.api.v1 import (
    health_router,
    exchanges_router,
    portfolio_router,
    bus_router,
    market_router,
    dynamic_assets_router,
    ai_providers_router,
    ema_scanner_router,
    image_uploader_router,
    telegram_router,
    quant_scanner_router,
    agent_templates_router,
    agent_charts_router,
    automation_router,
    trade_guard_router,
    risk_management_router,
    observability_router,
    oi_rank_router,
)
from app.common.logging import setup_logging
from app.realtime.server import create_socketio_app, create_socketio_server
from app.settings import get_settings


@asynccontextmanager
async def _lifespan(app: FastAPI):
    del app
    pending_entry_runtime = get_pending_entry_runtime()
    auto_add_runtime = get_auto_add_runtime()
    protection_reconciler_runtime = get_protection_reconciler_runtime()
    await pending_entry_runtime.start()
    await auto_add_runtime.start()
    await protection_reconciler_runtime.start()
    try:
        yield
    finally:
        await protection_reconciler_runtime.stop()
        await auto_add_runtime.stop()
        await pending_entry_runtime.stop()


def _create_api() -> FastAPI:
    settings = get_settings()

    api = FastAPI(
        title=settings.service_name,
        version=settings.version,
        lifespan=_lifespan,
    )
    register_request_id(api)
    register_exception_handlers(api)
    api.include_router(health_router, prefix="/api/v1", tags=["health"])
    api.include_router(exchanges_router, prefix="/api/v1")
    api.include_router(portfolio_router, prefix="/api/v1")
    api.include_router(bus_router, prefix="/api/v1")
    api.include_router(market_router, prefix="/api/v1")
    api.include_router(dynamic_assets_router, prefix="/api/v1")
    api.include_router(ai_providers_router, prefix="/api/v1")
    api.include_router(ema_scanner_router, prefix="/api/v1")
    api.include_router(image_uploader_router, prefix="/api/v1")
    api.include_router(telegram_router, prefix="/api/v1")
    api.include_router(quant_scanner_router, prefix="/api/v1")
    api.include_router(agent_templates_router, prefix="/api/v1")
    api.include_router(agent_charts_router, prefix="/api/v1")
    api.include_router(automation_router, prefix="/api/v1")
    api.include_router(trade_guard_router, prefix="/api/v1")
    api.include_router(risk_management_router, prefix="/api/v1")
    api.include_router(observability_router, prefix="/api/v1")
    api.include_router(oi_rank_router, prefix="/api/v1")

    @api.get("/")
    async def root() -> dict:
        return {"service": settings.service_name, "version": settings.version}

    return api


def create_app():
    settings = get_settings()
    setup_logging(settings.log_level)

    api = _create_api()
    sio = create_socketio_server(cors_origins=settings.cors_origins)

    return create_socketio_app(
        sio,
        api,
        socketio_path=settings.socketio_path,
    )


app = create_app()
