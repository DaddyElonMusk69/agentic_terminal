from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Union

from app.domain.portfolio.models import MarketCandle


@dataclass(frozen=True)
class ChartData:
    symbol: str
    timeframe: str
    candles: List[MarketCandle]


@dataclass(frozen=True)
class ChartTheme:
    up_color: str = "#26a69a"
    down_color: str = "#ef5350"
    grid_color: str = "#2a2e39"
    background_color: str = "#131722"
    text_color: str = "#787b86"
    edge_color: str = "#363a45"
    title_color: str = "#d1d4dc"


@dataclass(frozen=True)
class EmaOverlay:
    length: int
    color: str = "#2196F3"
    width: float = 1.2


@dataclass(frozen=True)
class VwapOverlay:
    color: str = "#9C27B0"
    width: float = 1.5


@dataclass(frozen=True)
class BollingerBandsOverlay:
    length: int = 20
    std_dev: float = 2.0
    color: str = "#7C4DFF"
    width: float = 0.8
    linestyle: str = "--"


@dataclass(frozen=True)
class AtrOverlay:
    length: int = 14
    color: str = "#FFA726"
    width: float = 1.1


ChartOverlay = Union[EmaOverlay, VwapOverlay, BollingerBandsOverlay, AtrOverlay]


@dataclass(frozen=True)
class ChartRenderRequest:
    data: ChartData
    overlays: List[ChartOverlay] = field(default_factory=list)
    theme: ChartTheme = field(default_factory=ChartTheme)
    candle_limit: Optional[int] = None
    show_volume: bool = True
    title: Optional[str] = None
    dpi: int = 150
    fig_ratio: tuple[int, int] = (12, 7)
    fig_scale: float = 1.2
    datetime_format: str = "%m-%d %H:%M"
    tight_layout: bool = True
