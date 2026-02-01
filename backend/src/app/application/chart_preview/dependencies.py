from functools import lru_cache

from app.application.chart_generator.service import ChartGenerator
from app.application.chart_preview.service import ChartPreviewService
from app.infrastructure.external.binance_client import BinanceClient


@lru_cache(maxsize=1)
def get_chart_preview_service() -> ChartPreviewService:
    return ChartPreviewService(
        chart_generator=ChartGenerator(),
        binance_client=BinanceClient(),
    )
