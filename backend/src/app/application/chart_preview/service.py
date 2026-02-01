from __future__ import annotations

import logging
from typing import List, Optional

from app.application.chart_generator.service import ChartGenerator
from app.domain.chart_generator.models import (
    BollingerBandsOverlay,
    ChartData,
    ChartRenderRequest,
    EmaOverlay,
)
from app.infrastructure.external.binance_client import BinanceClient

logger = logging.getLogger(__name__)

_EMA_COLOR_MAP = {
    36: "#FFFFFF",
    44: "#FFFFFF",
    144: "#FFD54F",
    169: "#FFD54F",
    576: "#42A5F5",
    676: "#42A5F5",
}
_DEFAULT_EMA_COLOR = "#FFFFFF"
_EXTRA_CANDLE_BUFFER = 50


class ChartPreviewService:
    def __init__(self, chart_generator: ChartGenerator, binance_client: BinanceClient) -> None:
        self._charts = chart_generator
        self._binance = binance_client
        self._last_error: Optional[str] = None

    def render_preview(
        self,
        symbol: str,
        interval: str,
        candle_limit: int,
        ema_lengths: Optional[List[int]] = None,
        show_bb: bool = True,
        bb_length: int = 20,
        bb_std: float = 2.0,
    ) -> Optional[bytes]:
        self._last_error = None
        symbol_key = (symbol or "").strip().upper() or "BTC"
        timeframe = (interval or "").strip()
        if not timeframe:
            self._last_error = "Interval is required"
            return None

        candle_limit = _clamp_int(candle_limit, 1, BinanceClient.MAX_KLINES_LIMIT)
        ema_list = _normalize_ema_lengths(ema_lengths)
        bb_length = _clamp_int(bb_length, 1, BinanceClient.MAX_KLINES_LIMIT)
        bb_std = float(bb_std) if bb_std and bb_std > 0 else 2.0

        overlays = _build_overlays(ema_list, show_bb, bb_length, bb_std)
        return self._render(symbol_key, timeframe, candle_limit, overlays, ema_list)

    def render_with_overlays(
        self,
        symbol: str,
        interval: str,
        candle_limit: int,
        overlays: Optional[List[object]] = None,
    ) -> Optional[bytes]:
        self._last_error = None
        symbol_key = (symbol or "").strip().upper() or "BTC"
        timeframe = (interval or "").strip()
        if not timeframe:
            self._last_error = "Interval is required"
            return None

        candle_limit = _clamp_int(candle_limit, 1, BinanceClient.MAX_KLINES_LIMIT)
        overlay_list = list(overlays or [])
        ema_list = _extract_ema_lengths(overlay_list)
        return self._render(symbol_key, timeframe, candle_limit, overlay_list, ema_list)

    def _render(
        self,
        symbol_key: str,
        timeframe: str,
        candle_limit: int,
        overlays: List[object],
        ema_lengths: List[int],
    ) -> Optional[bytes]:
        fetch_limit = _compute_fetch_limit(candle_limit, ema_lengths)
        candles = self._binance.fetch_candles(symbol_key, timeframe, fetch_limit)
        if not candles:
            self._last_error = self._binance.consume_last_error() or "No candle data returned"
            logger.warning("Chart preview failed for %s %s: %s", symbol_key, timeframe, self._last_error)
            return None
        if len(candles) < candle_limit:
            self._last_error = f"Insufficient candle data ({len(candles)}/{candle_limit})"
            logger.warning("Chart preview failed for %s %s: %s", symbol_key, timeframe, self._last_error)
            return None

        request = ChartRenderRequest(
            data=ChartData(
                symbol=symbol_key,
                timeframe=timeframe,
                candles=candles,
            ),
            overlays=overlays,
            candle_limit=candle_limit,
        )
        image_bytes = self._charts.render(request)
        if not image_bytes:
            self._last_error = "Chart render failed"
            logger.warning("Chart preview failed for %s %s: chart render failed", symbol_key, timeframe)
        return image_bytes

    def consume_last_error(self) -> Optional[str]:
        error = self._last_error
        self._last_error = None
        return error


def _clamp_int(value: int, minimum: int, maximum: int) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return minimum
    return max(minimum, min(numeric, maximum))


def _normalize_ema_lengths(values: Optional[List[int]]) -> List[int]:
    output: List[int] = []
    seen = set()
    for raw in values or []:
        try:
            length = int(raw)
        except (TypeError, ValueError):
            continue
        if length <= 0 or length in seen:
            continue
        seen.add(length)
        output.append(length)
    return output


def _extract_ema_lengths(overlays: List[object]) -> List[int]:
    lengths: List[int] = []
    seen = set()
    for overlay in overlays:
        if not isinstance(overlay, EmaOverlay):
            continue
        length = int(overlay.length)
        if length <= 0 or length in seen:
            continue
        seen.add(length)
        lengths.append(length)
    return lengths


def _compute_fetch_limit(candle_limit: int, ema_lengths: List[int]) -> int:
    max_ema = max(ema_lengths) if ema_lengths else 0
    fetch_limit = candle_limit + max_ema + _EXTRA_CANDLE_BUFFER
    fetch_limit = max(fetch_limit, candle_limit)
    return min(fetch_limit, BinanceClient.MAX_KLINES_LIMIT)


def _build_overlays(
    ema_lengths: List[int],
    show_bb: bool,
    bb_length: int,
    bb_std: float,
) -> List[object]:
    overlays: List[object] = []
    for length in ema_lengths:
        color = _EMA_COLOR_MAP.get(length, _DEFAULT_EMA_COLOR)
        overlays.append(EmaOverlay(length=length, color=color))
    if show_bb:
        overlays.append(BollingerBandsOverlay(length=bb_length, std_dev=bb_std))
    return overlays
