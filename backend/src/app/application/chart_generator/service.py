from __future__ import annotations

import io
import logging
import math
from typing import Optional, List

from app.domain.chart_generator.models import (
    AtrOverlay,
    ChartRenderRequest,
    EmaOverlay,
    VwapOverlay,
    BollingerBandsOverlay,
)

logger = logging.getLogger(__name__)


class ChartGenerator:
    def render(self, request: ChartRenderRequest) -> Optional[bytes]:
        if not request.data.candles:
            logger.warning("Chart render skipped: no candle data")
            return None

        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import pandas as pd
            import mplfinance as mpf
        except Exception as exc:  # pragma: no cover - optional dependency
            logger.error("Chart render failed: missing charting dependencies")
            logger.debug("Chart render dependency error: %s", exc)
            return None

        try:
            df = _candles_to_dataframe(request.data.candles)
            if df.empty:
                logger.warning("Chart render skipped: empty dataframe")
                return None

            candle_limit = request.candle_limit
            df_display = df.iloc[-candle_limit:] if candle_limit and len(df) > candle_limit else df
            ylim = _compute_overlay_ylim(df, df_display, request.overlays, candle_limit)
            addplots = _build_addplots(
                df,
                request.overlays,
                candle_limit,
                request.show_volume,
                (request.data.symbol, request.data.timeframe),
            )

            title = request.title or f"{request.data.symbol} ({request.data.timeframe.upper()})"
            style = _build_style(request)
            panel_ratios = _resolve_panel_ratios(request.overlays, request.show_volume)
            fig_ratio = (10, 10)
            xlim = _compute_xlim_padding(df_display)

            plot_kwargs = dict(
                type="candle",
                style=style,
                title=title,
                volume=request.show_volume,
                addplot=addplots if addplots else None,
                panel_ratios=panel_ratios,
                returnfig=True,
                figratio=fig_ratio,
                figscale=request.fig_scale,
                tight_layout=request.tight_layout,
                datetime_format="",
            )
            if ylim is not None:
                plot_kwargs["ylim"] = ylim
            if xlim is not None:
                plot_kwargs["xlim"] = xlim

            fig, axes = mpf.plot(
                df_display,
                **plot_kwargs,
            )

            fig.suptitle(
                title,
                fontsize=10,
                fontweight="bold",
                color=request.theme.title_color,
                y=0.98,
            )
            _add_ema_tunnel_legend(fig, request.overlays, request.theme.text_color)
            _apply_granular_price_levels(fig, df_display, request.theme)
            _hide_x_axis_labels(axes)

            buf = io.BytesIO()
            fig.savefig(
                buf,
                format="png",
                dpi=request.dpi,
                bbox_inches="tight",
                facecolor=request.theme.background_color,
            )
            plt.close(fig)

            buf.seek(0)
            image_bytes = buf.getvalue()
            buf.close()

            if len(image_bytes) < 1000:
                logger.warning("Chart render produced a tiny image (%s bytes)", len(image_bytes))
                return None

            return image_bytes
        except Exception as exc:
            logger.error("Chart render failed: %s", exc, exc_info=True)
            return None


def _candles_to_dataframe(candles):
    import pandas as pd

    df = pd.DataFrame(
        [
            {
                "Open": candle.open,
                "High": candle.high,
                "Low": candle.low,
                "Close": candle.close,
                "Volume": candle.volume,
            }
            for candle in candles
        ]
    )
    df.index = pd.to_datetime([candle.timestamp_ms for candle in candles], unit="ms")
    df.index.name = "Date"
    df = df.sort_index()
    df = df.dropna()
    return df


def _build_addplots(
    df,
    overlays,
    candle_limit: Optional[int],
    show_volume: bool,
    _context: Optional[tuple[str, str]] = None,
):
    import mplfinance as mpf

    addplots: List = []
    slice_index = -candle_limit if candle_limit and len(df) > candle_limit else None
    atr_panel = 2 if show_volume else 1

    for overlay in overlays:
        if isinstance(overlay, EmaOverlay):
            ema = df["Close"].ewm(span=overlay.length, adjust=False).mean()
            if slice_index is not None:
                ema = ema.iloc[slice_index:]
            addplots.append(mpf.make_addplot(ema, color=overlay.color, width=overlay.width))
        elif isinstance(overlay, VwapOverlay):
            typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
            vwap = (typical_price * df["Volume"]).cumsum() / df["Volume"].cumsum()
            if slice_index is not None:
                vwap = vwap.iloc[slice_index:]
            addplots.append(mpf.make_addplot(vwap, color=overlay.color, width=overlay.width))
        elif isinstance(overlay, BollingerBandsOverlay):
            mid = df["Close"].rolling(window=overlay.length).mean()
            std = df["Close"].rolling(window=overlay.length).std()
            upper = mid + (overlay.std_dev * std)
            lower = mid - (overlay.std_dev * std)
            if slice_index is not None:
                upper = upper.iloc[slice_index:]
                lower = lower.iloc[slice_index:]
            addplots.append(
                mpf.make_addplot(
                    upper,
                    color=overlay.color,
                    width=overlay.width,
                    linestyle=overlay.linestyle,
                )
            )
            addplots.append(
                mpf.make_addplot(
                    lower,
                    color=overlay.color,
                    width=overlay.width,
                    linestyle=overlay.linestyle,
                )
            )
        elif isinstance(overlay, AtrOverlay):
            atr = _compute_atr_series(df, overlay.length)
            if slice_index is not None:
                atr = atr.iloc[slice_index:]
            addplots.append(
                mpf.make_addplot(
                    atr,
                    panel=atr_panel,
                    color=overlay.color,
                    width=overlay.width,
                    ylabel=f"ATR({overlay.length})",
                )
            )

    return addplots


def _compute_atr_series(df, period: int):
    import pandas as pd

    safe_period = max(1, int(period))
    prev_close = df["Close"].shift(1)
    true_range = pd.concat(
        [
            (df["High"] - df["Low"]).abs(),
            (df["High"] - prev_close).abs(),
            (df["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / safe_period, adjust=False, min_periods=safe_period).mean()


def _resolve_panel_ratios(overlays, show_volume: bool):
    has_atr = any(isinstance(overlay, AtrOverlay) for overlay in overlays or [])
    if show_volume:
        return (7, 1, 1) if has_atr else (7, 1)
    if has_atr:
        return (7, 1)
    return None


def _build_style(request: ChartRenderRequest):
    import mplfinance as mpf

    theme = request.theme
    market_colors = mpf.make_marketcolors(
        up=theme.up_color,
        down=theme.down_color,
        edge="inherit",
        wick="inherit",
        volume="inherit",
    )
    return mpf.make_mpf_style(
        base_mpf_style="charles",
        marketcolors=market_colors,
        gridstyle="-",
        gridcolor=theme.grid_color,
        facecolor=theme.background_color,
        figcolor=theme.background_color,
        rc={
            "axes.labelcolor": theme.text_color,
            "axes.edgecolor": theme.edge_color,
            "xtick.color": theme.text_color,
            "ytick.color": theme.text_color,
        },
    )


_FAST_TUNNEL = {36, 44}
_MAIN_TUNNEL = {144, 169}
_SLOW_TUNNEL = {576, 676}


def _compute_xlim_padding(df_display) -> Optional[tuple]:
    try:
        if len(df_display.index) < 2:
            return None
        delta = df_display.index[-1] - df_display.index[-2]
        if delta.total_seconds() <= 0:
            return None
        padding = delta * 5
        return (df_display.index[0], df_display.index[-1] + padding)
    except Exception:
        return None


def _apply_granular_price_levels(fig, df_display, theme) -> None:
    """Add dense, granular y-axis price ticks and gridlines to the main price axis."""
    try:
        import matplotlib.ticker as mticker
    except Exception:
        return

    if not fig.axes:
        return

    ax = fig.axes[0]

    # Use the current axis ylim which already accounts for overlay-expanded ranges
    # (e.g. EMA lines outside the candle range). Fall back to candle data if needed.
    current_ylim = ax.get_ylim()
    try:
        candle_low = float(df_display["Low"].min())
        candle_high = float(df_display["High"].max())
    except Exception:
        candle_low, candle_high = current_ylim

    # Take the widest range between candle data and current ylim (overlay-aware)
    price_low = min(candle_low, current_ylim[0])
    price_high = max(candle_high, current_ylim[1])

    price_range = price_high - price_low
    if price_range <= 0:
        return

    major_interval = _compute_nice_tick_interval(price_range, target_ticks=20)
    minor_interval = major_interval / 4

    # Compute the major tick positions spanning the full visible range
    tick_start = math.floor(price_low / major_interval) * major_interval
    tick_end = math.ceil(price_high / major_interval) * major_interval
    major_ticks = []
    current = tick_start
    while current <= tick_end + major_interval * 0.01:
        major_ticks.append(current)
        current += major_interval

    ax.set_yticks(major_ticks)
    ax.yaxis.set_minor_locator(mticker.MultipleLocator(minor_interval))

    # Format tick labels based on price magnitude
    if price_high >= 100:
        fmt = "{x:,.0f}"
    elif price_high >= 1:
        fmt = "{x:,.2f}"
    elif price_high >= 0.01:
        fmt = "{x:,.4f}"
    else:
        fmt = "{x:,.6f}"
    ax.yaxis.set_major_formatter(mticker.StrMethodFormatter(fmt))

    # Style the major gridlines
    ax.grid(True, which="major", axis="y", color=theme.grid_color, linewidth=0.6, alpha=0.7)
    # Add subtle minor gridlines for even more granularity
    ax.grid(True, which="minor", axis="y", color=theme.grid_color, linewidth=0.3, alpha=0.35)

    # Ensure tick labels are visible and sized correctly
    ax.tick_params(axis="y", which="major", labelsize=7, colors=theme.text_color, length=4)
    ax.tick_params(axis="y", which="minor", length=2, colors=theme.text_color)

    # Preserve the full ylim (overlay-aware)
    padding = price_range * 0.02
    ax.set_ylim(price_low - padding, price_high + padding)


def _compute_nice_tick_interval(price_range: float, target_ticks: int = 20) -> float:
    """Compute a human-readable tick interval to produce approximately *target_ticks* ticks."""
    raw_interval = price_range / target_ticks
    magnitude = 10 ** math.floor(math.log10(raw_interval))
    residual = raw_interval / magnitude

    # Snap to the nearest "nice" number: 1, 2, 2.5, 5, or 10
    if residual <= 1.0:
        nice = 1.0
    elif residual <= 2.0:
        nice = 2.0
    elif residual <= 2.5:
        nice = 2.5
    elif residual <= 5.0:
        nice = 5.0
    else:
        nice = 10.0

    return nice * magnitude


def _hide_x_axis_labels(axes) -> None:
    if not axes:
        return
    for axis in axes:
        try:
            axis.tick_params(axis="x", which="both", bottom=False, labelbottom=False)
            axis.set_xlabel("")
        except Exception:
            continue


def _compute_overlay_ylim(df, df_display, overlays, candle_limit: Optional[int]):
    try:
        base_min = float(df_display["Low"].min())
        base_max = float(df_display["High"].max())
    except Exception:
        return None

    overlay_min = base_min
    overlay_max = base_max
    slice_index = -candle_limit if candle_limit and len(df) > candle_limit else None

    for overlay in overlays or []:
        if isinstance(overlay, EmaOverlay):
            series = df["Close"].ewm(span=overlay.length, adjust=False).mean()
        elif isinstance(overlay, VwapOverlay):
            typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
            series = (typical_price * df["Volume"]).cumsum() / df["Volume"].cumsum()
        elif isinstance(overlay, BollingerBandsOverlay):
            mid = df["Close"].rolling(window=overlay.length).mean()
            std = df["Close"].rolling(window=overlay.length).std()
            upper = mid + (overlay.std_dev * std)
            lower = mid - (overlay.std_dev * std)
            if slice_index is not None:
                upper = upper.iloc[slice_index:]
                lower = lower.iloc[slice_index:]
            try:
                overlay_min = min(overlay_min, float(lower.min()))
                overlay_max = max(overlay_max, float(upper.max()))
            except Exception:
                pass
            continue
        elif isinstance(overlay, AtrOverlay):
            continue
        else:
            continue

        if slice_index is not None:
            series = series.iloc[slice_index:]
        try:
            overlay_min = min(overlay_min, float(series.min()))
            overlay_max = max(overlay_max, float(series.max()))
        except Exception:
            pass

    if overlay_min == base_min and overlay_max == base_max:
        return None

    padding = (overlay_max - overlay_min) * 0.02
    if padding == 0:
        padding = max(1.0, abs(overlay_max) * 0.01)
    return (overlay_min - padding, overlay_max + padding)


def _add_ema_tunnel_legend(fig, overlays, text_color: str) -> None:
    if not overlays:
        return

    ema_lengths = [overlay.length for overlay in overlays if isinstance(overlay, EmaOverlay)]
    bb_overlay = next(
        (overlay for overlay in overlays if isinstance(overlay, BollingerBandsOverlay)),
        None,
    )
    atr_overlay = next((overlay for overlay in overlays if isinstance(overlay, AtrOverlay)), None)
    if not ema_lengths and bb_overlay is None and atr_overlay is None:
        return

    fast = any(length in _FAST_TUNNEL for length in ema_lengths)
    main = any(length in _MAIN_TUNNEL for length in ema_lengths)
    slow = any(length in _SLOW_TUNNEL for length in ema_lengths)

    if not (fast or main or slow or bb_overlay or atr_overlay):
        return

    try:
        from matplotlib.lines import Line2D
    except Exception:
        return

    handles = []
    labels = []
    if fast:
        handles.append(Line2D([0], [0], color="#FFFFFF", linewidth=2))
        labels.append("White = Fast tunnel")
    if main:
        handles.append(Line2D([0], [0], color="#FFD54F", linewidth=2))
        labels.append("Yellow = Main tunnel")
    if slow:
        handles.append(Line2D([0], [0], color="#42A5F5", linewidth=2))
        labels.append("Blue = Slow tunnel")
    if bb_overlay:
        handles.append(Line2D([0], [0], color=bb_overlay.color, linewidth=2, linestyle="--"))
        labels.append("Purple = BB band")
    if atr_overlay:
        handles.append(Line2D([0], [0], color=atr_overlay.color, linewidth=2))
        labels.append(f"Orange = ATR({atr_overlay.length})")

    if not handles:
        return

    ax = fig.axes[0] if fig.axes else None
    if ax is None:
        return

    legend = ax.legend(
        handles,
        labels,
        loc="upper left",
        frameon=True,
        fontsize=8,
    )
    legend.get_frame().set_facecolor("#0B0F14")
    legend.get_frame().set_edgecolor("#2a2e39")
    legend.get_frame().set_alpha(0.92)
    for handle, text in zip(handles, legend.get_texts()):
        if hasattr(handle, "get_color"):
            text.set_color(handle.get_color())
        else:
            text.set_color(text_color)
