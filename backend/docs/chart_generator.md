# Chart Generator

The chart generator is a data-only renderer. It accepts candle data and overlay
requirements, then outputs a PNG image. It does not fetch market data or decide
which charts to render.

## Inputs
- `ChartRenderRequest`
  - `data`: `ChartData` (symbol, timeframe, candles)
  - `overlays`: list of EMA, VWAP, and Bollinger Bands overlays
  - `candle_limit`: optional display window
  - `theme`: chart colors and background

## Output
- PNG image bytes or `None` on failure.

## Example
```python
from app.application.chart_generator import ChartGenerator
from app.domain.chart_generator import (
    ChartData,
    ChartRenderRequest,
    EmaOverlay,
    BollingerBandsOverlay,
)

request = ChartRenderRequest(
    data=ChartData(symbol="BTC/USDT", timeframe="2h", candles=candles),
    overlays=[EmaOverlay(length=20), EmaOverlay(length=50), BollingerBandsOverlay()],
    candle_limit=200,
)

image_bytes = ChartGenerator().render(request)
```

## Request Fields
- `data`: `ChartData` (symbol, timeframe, candles)
- `overlays`: list of overlay specs (`EmaOverlay`, `VwapOverlay`, `BollingerBandsOverlay`)
- `theme`: `ChartTheme` (colors and styling)
- `candle_limit`: optional display window size
- `show_volume`: include volume subplot
- `title`: override chart title
- `dpi`: render resolution
- `fig_ratio`: figure width/height ratio
- `fig_scale`: figure scale multiplier
- `datetime_format`: x-axis date format
- `tight_layout`: apply tight layout

## Notes
- EMA/VWAP/BB overlays are calculated on the full series, then trimmed to the
  display window for stable warmup.
- The module intentionally avoids fetching data or handling multi-chart layouts.
