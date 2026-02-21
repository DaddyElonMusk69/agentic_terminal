from app.api.v1.health import router as health_router
from app.api.v1.exchanges import router as exchanges_router
from app.api.v1.portfolio import router as portfolio_router
from app.api.v1.bus import router as bus_router
from app.api.v1.market import router as market_router
from app.api.v1.dynamic_assets import router as dynamic_assets_router
from app.api.v1.ai_providers import router as ai_providers_router
from app.api.v1.ema_scanner import router as ema_scanner_router
from app.api.v1.image_uploader import router as image_uploader_router
from app.api.v1.telegram import router as telegram_router
from app.api.v1.quant_scanner import router as quant_scanner_router
from app.api.v1.agent_templates import router as agent_templates_router
from app.api.v1.agent_charts import router as agent_charts_router
from app.api.v1.automation import router as automation_router
from app.api.v1.trade_guard import router as trade_guard_router
from app.api.v1.risk_management import router as risk_management_router
from app.api.v1.observability import router as observability_router
from app.api.v1.oi_rank import router as oi_rank_router

__all__ = [
    "health_router",
    "exchanges_router",
    "portfolio_router",
    "bus_router",
    "market_router",
    "dynamic_assets_router",
    "ai_providers_router",
    "ema_scanner_router",
    "image_uploader_router",
    "telegram_router",
    "quant_scanner_router",
    "agent_templates_router",
    "agent_charts_router",
    "automation_router",
    "trade_guard_router",
    "risk_management_router",
    "observability_router",
    "oi_rank_router",
]
