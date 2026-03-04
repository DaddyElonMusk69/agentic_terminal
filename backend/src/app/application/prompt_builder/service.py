from __future__ import annotations

import asyncio
import json
import re
from dataclasses import asdict, is_dataclass
from collections import OrderedDict
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

from app.application.chart_preview.service import ChartPreviewService
from app.application.portfolio.service import PortfolioService
from app.application.risk_management.config_service import RiskManagementConfigService
from app.domain.chart_generator.models import (
    BollingerBandsOverlay,
    EmaOverlay,
    VwapOverlay,
)
from app.application.image_uploader.service import ImageUploaderService
from app.domain.prompt_builder.interfaces import PromptTemplateRepository, QuantSnapshotProvider
from app.domain.prompt_builder.models import (
    ChartRequest,
    PromptBuildRequest,
    PromptBuildResult,
    PromptTemplate,
)
from app.infrastructure.external.codex_temp_images import CodexTempImageStore


class PromptBuildError(RuntimeError):
    pass


class PromptBuilderService:
    def __init__(
        self,
        template_repository: PromptTemplateRepository,
        quant_provider: QuantSnapshotProvider,
        chart_preview_service: ChartPreviewService,
        uploader_service: ImageUploaderService,
        portfolio_service: PortfolioService,
        risk_config_service: RiskManagementConfigService,
        codex_temp_images: CodexTempImageStore | None = None,
        upload_concurrency: int = 4,
        recent_trades_limit: int = 10,
    ) -> None:
        self._templates = template_repository
        self._quant = quant_provider
        self._chart_preview = chart_preview_service
        self._uploader_service = uploader_service
        self._codex_temp_images = codex_temp_images
        self._upload_concurrency = max(1, int(upload_concurrency))
        self._portfolio_service = portfolio_service
        self._risk_config_service = risk_config_service
        self._recent_trades_limit = max(1, int(recent_trades_limit))
        self._peak_roe_tracker: Dict[str, float] = {}

    async def build(self, request: PromptBuildRequest) -> PromptBuildResult:
        template = await self._load_template(request.template_id)
        if not request.tickers or not request.intervals:
            raise PromptBuildError("tickers and intervals are required")

        defaults = template.chart_defaults or {}
        data_selections = _resolve_data_selections(defaults)
        field_selections = _resolve_field_selections(defaults)

        quant_fields = request.quant_fields or template.quant_fields
        data_payload, _ = self._build_quant_payload(
            request.tickers,
            request.intervals,
            quant_fields,
        )

        if data_selections is None or "quantitative_signals" not in data_selections:
            data_payload.pop("quant_data", None)

        context_payload = await self._build_context_payload(
            data_selections,
            field_selections,
        )
        if context_payload:
            data_payload.update(context_payload)

        chart_items: List[Dict[str, Any]] = []
        if data_selections is None or "chart_snapshots" in data_selections:
            chart_items = await self._build_charts(
                request.tickers,
                request.chart_requests,
                template.chart_defaults,
                provider=request.provider,
            )
            _assert_required_charts(request.tickers, request.chart_requests, chart_items)
            if chart_items:
                data_payload["chart_snapshots"] = chart_items

        data_payload = _order_prompt_payload(data_payload)

        intro = _safe_format(template.intro, **request.template_context)
        response_format = _safe_format(template.response_format, **request.template_context)
        prompt_text = _assemble_prompt(intro, data_payload, response_format)

        return PromptBuildResult(
            request_id=request.request_id,
            template_id=template.id,
            template_name=template.name,
            prompt_text=prompt_text,
            data=data_payload,
            chart_items=chart_items,
        )

    async def _build_context_payload(
        self,
        data_selections: Optional[List[str]],
        field_selections: Dict[str, List[str]],
    ) -> Dict[str, Any]:
        if not data_selections:
            return {}

        selections = set(data_selections)
        needs_snapshot = bool(
            selections
            & {
                "portfolio_overview",
                "trade_mandate",
                "account_state",
                "open_positions",
            }
        )
        needs_daily_pnl = bool(selections & {"account_state", "recent_completed_trades"})
        needs_risk_config = bool(selections & {"portfolio_overview", "trade_mandate", "account_state"})
        needs_open_orders = bool(selections & {"open_positions"})
        needs_recent_trades = bool(selections & {"recent_completed_trades"})

        snapshot = None
        snapshot_error = None
        if needs_snapshot:
            try:
                snapshot = await self._portfolio_service.get_portfolio_snapshot()
            except Exception as exc:
                snapshot_error = str(exc)

        daily_pnl = None
        daily_pnl_error = None
        if needs_daily_pnl:
            try:
                daily_pnl = await self._portfolio_service.get_daily_pnl()
            except Exception as exc:
                daily_pnl_error = str(exc)

        open_orders: List[dict] = []
        if needs_open_orders:
            try:
                open_orders = await self._portfolio_service.get_open_orders()
            except Exception:
                open_orders = []

        recent_trades: List[dict] = []
        recent_trades_error = None
        if needs_recent_trades:
            try:
                recent_trades = await self._portfolio_service.get_recent_trades(self._recent_trades_limit)
            except Exception as exc:
                recent_trades_error = str(exc)

        risk_config = None
        if needs_risk_config:
            try:
                risk_config = await self._risk_config_service.get_config()
            except Exception:
                risk_config = None

        account_value = snapshot.state.account_value if snapshot else None
        exposure_pct = float(risk_config.exposure_pct) if risk_config else None
        exposure_usd = None
        if account_value is not None and exposure_pct is not None:
            exposure_usd = account_value * (exposure_pct / 100.0)

        daily_target_pct = None
        daily_target_usd = None
        goal_usd = float(risk_config.final_goal_usd) if risk_config else None
        days_left = _days_left(risk_config.goal_deadline) if risk_config else None
        if account_value is not None and goal_usd is not None and goal_usd > 0 and days_left:
            if goal_usd <= account_value:
                daily_target_pct = 0.0
                daily_target_usd = 0.0
            else:
                rate = (goal_usd / account_value) ** (1 / days_left) - 1
                daily_target_pct = rate * 100.0
                daily_target_usd = account_value * rate

        progress_pct = None
        if account_value is not None and goal_usd is not None and goal_usd > 0:
            progress_pct = (account_value / goal_usd) * 100.0

        data: Dict[str, Any] = {}

        if "portfolio_overview" in selections:
            portfolio_overview = {
                "account_value": account_value,
                "final_goal": goal_usd,
                "goal_progress": progress_pct,
                "days_left_for_achieving_goal": days_left,
                "daily_growth_target": daily_target_pct,
                "daily_growth_target_dollar_value": daily_target_usd,
            }
            if snapshot is None and snapshot_error:
                portfolio_overview["status"] = snapshot_error
            portfolio_overview = _filter_fields_if_needed(
                portfolio_overview,
                field_selections.get("portfolio_overview"),
            )
            data["portfolio_overview"] = _normalize_values(portfolio_overview)

        if "trade_mandate" in selections:
            trade_mandate = {
                "max_portfolio_exposure": exposure_pct,
                "max_available_margin": exposure_usd,
            }
            if daily_target_usd is not None and exposure_usd:
                trade_mandate["target_profit_on_max_exposure"] = (
                    daily_target_usd / exposure_usd * 100.0 if exposure_usd > 0 else None
                )
            if snapshot is None and snapshot_error:
                trade_mandate["status"] = snapshot_error
            trade_mandate = _filter_fields_if_needed(
                trade_mandate,
                field_selections.get("trade_mandate"),
            )
            data["trade_mandate"] = _normalize_values(trade_mandate)

        if "account_state" in selections:
            realized_pnl_today = daily_pnl.realized_pnl if daily_pnl else None
            trades_today = daily_pnl.trade_count if daily_pnl else None
            available_margin_left = None
            if exposure_usd is not None and snapshot is not None:
                available_margin_left = exposure_usd - snapshot.state.total_margin_used
            pnl_gap_usd = None
            if daily_target_usd is not None and realized_pnl_today is not None:
                pnl_gap_usd = daily_target_usd - realized_pnl_today
            daily_goal_met = None
            if daily_target_usd is not None and realized_pnl_today is not None:
                daily_goal_met = realized_pnl_today >= daily_target_usd

            account_state = {
                "realized_pnl_today": realized_pnl_today,
                "trades_today": trades_today,
                "available_margin_left": available_margin_left,
                "daily_goal_met": daily_goal_met,
                "pnl_gap_usd": pnl_gap_usd,
            }
            if daily_pnl is None and daily_pnl_error:
                account_state["status"] = daily_pnl_error
            account_state = _filter_fields_if_needed(
                account_state,
                field_selections.get("account_state"),
            )
            data["account_state"] = _normalize_values(account_state)

        if "recent_completed_trades" in selections:
            trades_payload = _build_recent_trades_payload(
                recent_trades,
                recent_trades_error,
            )
            trades_payload = _filter_fields_if_needed(
                trades_payload,
                field_selections.get("recent_completed_trades"),
            )
            data["recent_completed_trades"] = _normalize_values(trades_payload)

        if "open_positions" in selections:
            positions_payload = _build_open_positions_payload(
                snapshot,
                snapshot_error,
                open_orders,
                self._peak_roe_tracker,
            )
            allowed_fields = field_selections.get("open_positions")
            if allowed_fields:
                filtered_positions = {}
                for symbol, position in positions_payload.items():
                    if isinstance(position, dict) and "status" not in position:
                        filtered_positions[symbol] = _filter_fields_if_needed(position, allowed_fields)
                    else:
                        filtered_positions[symbol] = position
                positions_payload = filtered_positions
            data["open_positions"] = _normalize_values(positions_payload)

        return data

    async def _load_template(self, template_id: Optional[int]) -> PromptTemplate:
        template = None
        if template_id:
            template = await self._templates.get_by_id(template_id)
        if template is None:
            template = await self._templates.get_default()
        if template is None:
            raise PromptBuildError("prompt template not found")
        return template

    def _build_quant_payload(
        self,
        tickers: Sequence[str],
        intervals: Sequence[str],
        quant_fields: Optional[List[str]],
    ) -> tuple[Dict[str, Any], Dict[str, Dict[str, Any]]]:
        now = datetime.now(timezone.utc)
        payload: Dict[str, Any] = {
            "timestamp": now.isoformat(),
            "quant_data": [],
        }

        snapshots: Dict[str, Dict[str, Any]] = {}
        missing: List[str] = []

        for ticker in tickers:
            ticker_key = ticker.strip().upper()
            snapshot_bucket: Dict[str, Any] = {}
            for interval in intervals:
                snapshot = self._quant.get_snapshot(ticker_key, interval)
                if snapshot is None:
                    missing.append(f"{ticker_key}@{interval}")
                    continue
                snapshot_dict = _snapshot_to_dict(snapshot, quant_fields)
                flat_row = _flatten_snapshot_dict(snapshot_dict, ticker_key, interval)
                payload["quant_data"].append(flat_row)
                snapshot_bucket[interval] = snapshot
            snapshots[ticker_key] = snapshot_bucket

        if missing:
            raise PromptBuildError(f"missing quant snapshots: {', '.join(missing)}")

        return payload, snapshots

    async def _build_charts(
        self,
        tickers: Sequence[str],
        chart_requests: Sequence[ChartRequest],
        chart_defaults: Optional[Dict[str, Any]],
        provider: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not chart_requests:
            return []

        defaults = chart_defaults or {}
        chart_items: List[Dict[str, Any]] = []
        upload_jobs: List[tuple[str, str, int, bytes]] = []

        for ticker in tickers:
            ticker_key = ticker.strip().upper()
            for request in chart_requests:
                interval = request.interval
                if not interval:
                    continue

                overlays = _resolve_overlays(request.overlays, defaults)
                candle_limit = _resolve_candle_limit(
                    interval=interval,
                    request_candles=request.candles,
                    defaults=defaults,
                )

                image_bytes = self._chart_preview.render_with_overlays(
                    symbol=ticker_key,
                    interval=interval,
                    candle_limit=candle_limit,
                    overlays=overlays,
                )
                if not image_bytes:
                    continue

                upload_jobs.append((ticker_key, interval, candle_limit, image_bytes))

        if not upload_jobs:
            return []

        provider_id = (provider or "").strip().lower()
        if provider_id == "codex":
            if self._codex_temp_images is None:
                raise PromptBuildError("codex temp image store is not configured")
            for ticker_key, interval, candle_limit, image_bytes in upload_jobs:
                name = f"{ticker_key}_{interval}_{candle_limit}_{int(datetime.now(timezone.utc).timestamp())}"
                local_path = self._codex_temp_images.save_png(image_bytes, name)
                chart_items.append(
                    {
                        "type": "input_image",
                        "image_url": local_path,
                        "ticker": ticker_key,
                        "interval": interval,
                    }
                )
            return chart_items

        uploader = await self._uploader_service.get_uploader()
        semaphore = asyncio.Semaphore(self._upload_concurrency)

        async def _upload(job: tuple[str, str, int, bytes]) -> Optional[Dict[str, Any]]:
            ticker_key, interval, candle_limit, image_bytes = job
            name = f"{ticker_key}_{interval}_{candle_limit}_{int(datetime.now(timezone.utc).timestamp())}"
            async with semaphore:
                url = await uploader.upload(image_bytes, name)
            if not url:
                return None
            return {
                "type": "input_image",
                "image_url": url,
                "ticker": ticker_key,
                "interval": interval,
            }

        results = await asyncio.gather(
            *[_upload(job) for job in upload_jobs],
            return_exceptions=False,
        )

        for item in results:
            if item:
                chart_items.append(item)

        if hasattr(uploader, "close"):
            close = getattr(uploader, "close")
            if callable(close):
                await close()

        return chart_items


def _assemble_prompt(intro: str, data: Dict[str, Any], response_format: str) -> str:
    data_json = json.dumps(data, indent=2, default=str)
    return f"{intro}\n\n{data_json}\n\n{response_format}"


def _safe_format(template: str, **kwargs) -> str:
    if not template:
        return ""

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return str(kwargs.get(key, match.group(0)))

    pattern = r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}"
    return re.sub(pattern, replace, template)


def _snapshot_to_dict(snapshot: Any, quant_fields: Optional[Iterable[str]]) -> Dict[str, Any]:
    raw = _serialize_value(asdict(snapshot))
    if not quant_fields:
        return _normalize_snapshot_dict(raw)

    allowed = {"symbol", "timeframe", "timestamp"}
    allowed.update(quant_fields)
    filtered = {key: raw.get(key) for key in allowed if key in raw}
    return _normalize_snapshot_dict(filtered)


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return _serialize_value(asdict(value))
    if isinstance(value, dict):
        return {key: _serialize_value(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    return value


_CURRENCY_HINTS = {
    "price",
    "prices",
    "mark_price",
    "entry",
    "exit",
    "open",
    "high",
    "low",
    "close",
    "pnl",
    "margin",
    "equity",
    "netflow",
    "net_depth",
    "open_interest",
    "oi",
    "cvd",
    "value",
}

_NON_CURRENCY_HINTS = {
    "pct",
    "percent",
    "ratio",
    "z_score",
    "std",
    "std_dev",
    "slope",
    "distance",
    "imbalance",
    "count",
    "candle_count",
    "timestamp",
    "time",
    "lookback",
    "period",
    "volume",
}


def _normalize_snapshot_dict(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = dict(snapshot)

    order_book = cleaned.get("order_book")
    if isinstance(order_book, dict):
        for key in (
            "mid_price",
            "range_pct",
            "best_bid",
            "best_ask",
            "bid_volume_usd",
            "ask_volume_usd",
            "bid_volume",
            "ask_volume",
        ):
            order_book.pop(key, None)
        cleaned["order_book"] = order_book

    vwap = cleaned.get("vwap")
    if isinstance(vwap, dict):
        vwap.pop("candle_count", None)
        cleaned["vwap"] = vwap

    atr = cleaned.get("atr")
    if isinstance(atr, dict):
        atr.pop("period", None)
        atr.pop("lookback", None)
        cleaned["atr"] = atr

    anomalies = cleaned.get("anomalies")
    if isinstance(anomalies, dict):
        filtered: Dict[str, Any] = {}
        for key, result in anomalies.items():
            if not isinstance(result, dict):
                continue
            if not result.get("is_significant"):
                continue
            value = result.get("current_value")
            if value is None:
                continue
            filtered[key] = value
        if filtered:
            cleaned["anomalies"] = filtered
        else:
            cleaned.pop("anomalies", None)
    else:
        cleaned.pop("anomalies", None)

    return _normalize_values(cleaned)


def _normalize_values(value: Any, key: str = "", parent: str = "") -> Any:
    if isinstance(value, dict):
        output: Dict[str, Any] = {}
        for child_key, child_value in value.items():
            output[child_key] = _normalize_values(child_value, child_key, key)
        return output
    if isinstance(value, list):
        return [_normalize_values(item, key, parent) for item in value]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return _format_number(value, key, parent)
    return value


def _format_number(value: float | int, key: str, parent: str) -> Any:
    if isinstance(value, bool):
        return value

    if isinstance(value, int) and not isinstance(value, bool):
        if _is_currency_key(key, parent):
            return f"${value:,.2f}"
        return value

    numeric = float(value)
    if _is_currency_key(key, parent):
        return f"${numeric:,.2f}"
    return round(numeric, 2)


def _is_currency_key(key: str, parent: str) -> bool:
    key_lower = key.lower()
    parent_lower = parent.lower()

    if any(hint in key_lower for hint in _NON_CURRENCY_HINTS):
        return False
    if any(hint in parent_lower for hint in _NON_CURRENCY_HINTS):
        return False

    if "usd" in key_lower or key_lower.endswith("_usd"):
        return True
    if any(hint in key_lower for hint in _CURRENCY_HINTS):
        return True
    if any(hint in parent_lower for hint in _CURRENCY_HINTS):
        return True
    return False


def _flatten_snapshot_dict(snapshot: Dict[str, Any], ticker: str, interval: str) -> Dict[str, Any]:
    ordered = OrderedDict()
    ordered["ticker"] = ticker
    ordered["interval"] = interval

    preferred_order = [
        "price_current",
        "price_slope",
        "price_slope_z",
        "oi_current",
        "oi_slope",
        "oi_slope_z",
        "cvd_current",
        "cvd_slope",
        "cvd_slope_z",
    ]

    latest_cvd_delta = None
    if isinstance(snapshot.get("cvd_deltas"), list) and snapshot["cvd_deltas"]:
        latest_cvd_delta = snapshot["cvd_deltas"][-1]

    for key in preferred_order:
        if key in snapshot:
            ordered[key] = snapshot[key]
    if latest_cvd_delta is not None:
        ordered["cvd_delta"] = latest_cvd_delta

    order_book = snapshot.get("order_book")
    if isinstance(order_book, dict):
        for sub_key in ("net_depth_usd", "imbalance_pct", "obi_ratio"):
            if sub_key in order_book:
                ordered[sub_key] = order_book[sub_key]

    vwap = snapshot.get("vwap")
    if isinstance(vwap, dict):
        if "value" in vwap:
            ordered["vwap"] = vwap["value"]
        if "distance" in vwap:
            ordered["vwap_distance"] = vwap["distance"]

    atr = snapshot.get("atr")
    if isinstance(atr, dict):
        if "value" in atr:
            ordered["atr"] = atr["value"]
        if "slope_pct" in atr:
            ordered["atr_slope_pct"] = atr["slope_pct"]
        if "z_score" in atr:
            ordered["atr_z_score"] = atr["z_score"]

    funding = snapshot.get("funding_rate")
    if isinstance(funding, dict):
        if "rate" in funding:
            ordered["funding_rate"] = funding["rate"]
        if "mark_price" in funding:
            ordered["funding_mark_price"] = funding["mark_price"]

    netflow = snapshot.get("netflow")
    if isinstance(netflow, dict):
        for sub_key in (
            "total_netflow",
            "institution_netflow",
            "retail_netflow",
            "flow_regime",
            "dominant_flow",
        ):
            if sub_key in netflow:
                ordered[sub_key] = netflow[sub_key]

    anomalies = snapshot.get("anomalies")
    if isinstance(anomalies, dict):
        for sub_key, value in anomalies.items():
            ordered[f"anomaly_{sub_key}"] = value

    # Append remaining simple fields not already captured
    for key, value in snapshot.items():
        if key in ordered:
            continue
        if key in ("candles", "prices", "open_interest", "cvd", "cvd_deltas"):
            continue
        if isinstance(value, (dict, list)):
            continue
        ordered[key] = value

    return dict(ordered)


_VEGAS_EMA_COLOR_MAP = {
    36: "#FFFFFF",
    44: "#FFFFFF",
    144: "#FFD54F",
    169: "#FFD54F",
    576: "#42A5F5",
    676: "#42A5F5",
}
_DEFAULT_EMA_COLOR = "#FFFFFF"


def _resolve_overlays(
    overlays: Optional[Sequence[str]],
    defaults: Dict[str, Any],
) -> List[Any]:
    overlay_names = [str(item).strip() for item in (overlays or defaults.get("overlays") or [])]
    overlay_keys = {name.lower() for name in overlay_names if name}

    if "ema" not in overlay_keys and (_has_vegas_tunnels(defaults) or defaults.get("ema_lengths")):
        overlay_names.append("ema")
        overlay_keys.add("ema")

    if "bb" not in overlay_keys and defaults.get("vegas_show_bb") is True:
        overlay_names.append("bb")

    resolved: List[Any] = []

    for name in overlay_names:
        key = str(name).lower().strip()
        if key == "ema":
            lengths = _resolve_ema_lengths(defaults)
            if not lengths:
                continue
            colors = _resolve_ema_colors(defaults, lengths)
            for length, color in zip(lengths, colors):
                resolved.append(EmaOverlay(length=int(length), color=str(color)))
        elif key == "bb":
            length = _resolve_bb_length(defaults)
            std_dev = _resolve_bb_std(defaults)
            resolved.append(BollingerBandsOverlay(length=length, std_dev=std_dev))
        elif key == "vwap":
            resolved.append(VwapOverlay())

    return resolved


def _resolve_data_selections(defaults: Dict[str, Any]) -> Optional[List[str]]:
    selections = defaults.get("data_selections")
    if isinstance(selections, list):
        normalized = [str(item) for item in selections if str(item).strip()]
        return normalized
    return [
        "portfolio_overview",
        "trade_mandate",
        "account_state",
        "recent_completed_trades",
        "chart_snapshots",
        "open_positions",
        "quantitative_signals",
    ]


def _resolve_field_selections(defaults: Dict[str, Any]) -> Dict[str, List[str]]:
    raw = defaults.get("field_selections")
    if not isinstance(raw, dict):
        return {}
    output: Dict[str, List[str]] = {}
    for key, value in raw.items():
        if not isinstance(value, list):
            continue
        fields = [str(item) for item in value if str(item).strip()]
        if fields:
            output[str(key)] = fields
    return output


def _filter_fields_if_needed(data: Dict[str, Any], allowed_fields: Optional[List[str]]) -> Dict[str, Any]:
    if not allowed_fields:
        return data
    return {key: value for key, value in data.items() if key in allowed_fields}


def _order_prompt_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    ordered = OrderedDict()
    if "timestamp" in payload:
        ordered["timestamp"] = payload["timestamp"]

    order_map = [
        ("portfolio_overview", "portfolio_overview"),
        ("trade_mandate", "trade_mandate"),
        ("account_state", "account_state"),
        ("recent_completed_trades", "recent_completed_trades"),
        ("chart_snapshots", "chart_snapshots"),
        ("open_positions", "open_positions"),
        ("quantitative_signals", "quant_data"),
        ("what_not_to_do_list", "what_not_to_do_list"),
        ("llm_considerations", "llm_considerations"),
    ]

    for _, key in order_map:
        if key in payload:
            ordered[key] = payload[key]

    for key, value in payload.items():
        if key in ordered:
            continue
        ordered[key] = value

    return dict(ordered)


def _index_orders(orders: List[dict]) -> Dict[str, List[dict]]:
    index: Dict[str, List[dict]] = {}
    for order in orders:
        if not isinstance(order, dict):
            continue
        symbol = _normalize_order_symbol(order.get("symbol"))
        if not symbol:
            continue
        index.setdefault(symbol, []).append(order)
    return index


def _normalize_order_symbol(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    symbol = value.strip()
    if not symbol:
        return ""
    if ":" in symbol:
        return symbol.split(":", 1)[0]
    return symbol


def _assert_required_charts(
    tickers: Sequence[str],
    chart_requests: Sequence[ChartRequest],
    chart_items: Sequence[Dict[str, Any]],
) -> None:
    expected = _expected_chart_keys(tickers, chart_requests)
    if not expected:
        return

    actual = _chart_item_keys(chart_items)
    missing = [f"{ticker}@{interval}" for ticker, interval in expected if (ticker, interval) not in actual]
    if missing:
        raise PromptBuildError(f"missing chart snapshots: {', '.join(missing)}")


def _expected_chart_keys(
    tickers: Sequence[str],
    chart_requests: Sequence[ChartRequest],
) -> List[tuple[str, str]]:
    expected: List[tuple[str, str]] = []
    seen = set()
    for ticker in tickers:
        for request in chart_requests:
            key = _normalize_chart_key(ticker, request.interval)
            if not key or key in seen:
                continue
            seen.add(key)
            expected.append(key)
    return expected


def _chart_item_keys(chart_items: Sequence[Dict[str, Any]]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for item in chart_items:
        if not isinstance(item, dict):
            continue
        key = _normalize_chart_key(item.get("ticker"), item.get("interval"))
        if key:
            keys.add(key)
    return keys


def _normalize_chart_key(ticker: Any, interval: Any) -> Optional[tuple[str, str]]:
    ticker_key = str(ticker or "").strip().upper()
    interval_key = str(interval or "").strip()
    if not ticker_key or not interval_key:
        return None
    return ticker_key, interval_key


def _extract_sl_tp(orders: List[dict]) -> tuple[Optional[float], Optional[float]]:
    stop_loss = None
    take_profit = None
    for order in orders:
        if not isinstance(order, dict):
            continue
        info = order.get("info") if isinstance(order.get("info"), dict) else {}
        order_type = str(order.get("type") or info.get("type") or "").lower()
        stop_price = (
            order.get("stopPrice")
            or order.get("triggerPrice")
            or info.get("stopPrice")
            or info.get("triggerPrice")
        )
        price = order.get("price") or info.get("price")
        candidate = _safe_float(stop_price if stop_price is not None else price)
        if candidate is None:
            continue
        if "take" in order_type:
            if take_profit is None:
                take_profit = candidate
            continue
        if "stop" in order_type:
            if stop_loss is None:
                stop_loss = candidate
            continue
    return stop_loss, take_profit


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_duration(opened_at: Optional[datetime]) -> Optional[str]:
    if not opened_at:
        return None
    delta = datetime.now(timezone.utc) - opened_at
    total_minutes = int(delta.total_seconds() / 60)
    if total_minutes < 0:
        return None
    if total_minutes < 60:
        return f"{total_minutes}m"
    if total_minutes < 1440:
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours}h{minutes}m"
    days = total_minutes // 1440
    hours = (total_minutes % 1440) // 60
    return f"{days}d{hours}h"


def _build_recent_trades_payload(
    trades: List[dict],
    error_message: Optional[str],
) -> Dict[str, Any]:
    if not trades:
        return {"status": error_message or "No recent trades"}

    normalized: List[str] = []
    for idx, trade in enumerate(trades, start=1):
        if not isinstance(trade, dict):
            continue
        normalized.append(_format_trade_summary(idx, trade))

    return {
        "recent_completed_trades": normalized,
        "total_trades_in_period": len(normalized),
    }


def _format_trade_summary(index: int, trade: Dict[str, Any]) -> str:
    symbol = str(trade.get("symbol") or trade.get("coin") or "").strip()
    direction = str(trade.get("direction") or "").lower() or "unknown"

    entry_price = _safe_float(trade.get("entry_price"))
    exit_price = _safe_float(trade.get("exit_price"))
    pnl_value = _safe_float(trade.get("pnl"))
    roi_pct = _safe_float(trade.get("roi_pct"))

    entry_time = _safe_float(trade.get("entry_time"))
    exit_time = _safe_float(trade.get("exit_time"))
    duration_minutes = _safe_float(trade.get("duration_minutes"))

    entry_str = _format_trade_time(entry_time)
    exit_str = _format_trade_time(exit_time)
    duration_str = _format_trade_duration(duration_minutes, entry_time, exit_time)

    entry_fmt = _format_trade_price(entry_price)
    exit_fmt = _format_trade_price(exit_price)

    if pnl_value is None:
        pnl_value = 0.0
    if pnl_value >= 0:
        result_word = "Profit"
        pnl_sign = "+"
    else:
        result_word = "Loss"
        pnl_sign = ""

    roi_fmt = _format_trade_roi(roi_pct, pnl_sign)
    return (
        f"{index}. {symbol} {direction} | Entry {entry_fmt} Exit {exit_fmt} | "
        f"{result_word}: {pnl_sign}{pnl_value:.2f} USDT ({roi_fmt}) | "
        f"{entry_str}→{exit_str} UTC ({duration_str})"
    )


def _format_trade_time(timestamp_ms: Optional[float]) -> str:
    if not timestamp_ms:
        return "unknown"
    try:
        ts = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    except Exception:
        return "unknown"
    return ts.strftime("%m-%d %H:%M")


def _format_trade_duration(
    duration_minutes: Optional[float],
    entry_time_ms: Optional[float],
    exit_time_ms: Optional[float],
) -> str:
    minutes = None
    if duration_minutes is not None and duration_minutes >= 0:
        minutes = int(duration_minutes)
    elif entry_time_ms and exit_time_ms:
        try:
            minutes = int(max(0, (exit_time_ms - entry_time_ms) / 60000))
        except Exception:
            minutes = None

    if minutes is None:
        return "0m"
    if minutes < 60:
        return f"{minutes}m"
    if minutes < 1440:
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours}h{mins}m"
    days = minutes // 1440
    hours = (minutes % 1440) // 60
    return f"{days}d{hours}h"


def _format_trade_price(value: Optional[float]) -> str:
    if value is None:
        return "0.000000"
    if value >= 1000:
        return f"{value:.1f}"
    if value >= 1:
        return f"{value:.4f}"
    return f"{value:.6f}"


def _format_trade_roi(value: Optional[float], pnl_sign: str) -> str:
    if value is None:
        value = 0.0
    return f"{pnl_sign}{value:.2f}%"


def _build_open_positions_payload(
    snapshot: Optional[Any],
    error_message: Optional[str],
    open_orders: List[dict],
    peak_roe_tracker: Dict[str, float],
) -> Dict[str, Any]:
    if snapshot is None:
        return {"status": error_message or "No active account configured"}

    positions = snapshot.positions or []
    if not positions:
        return {"status": "No open positions"}

    order_index = _index_orders(open_orders)
    payload: Dict[str, Any] = {}
    for position in positions:
        symbol = position.symbol
        margin_used = position.margin
        if margin_used is None and position.entry_price and position.leverage:
            try:
                margin_used = abs(position.size * position.entry_price) / float(position.leverage)
            except Exception:
                margin_used = None

        roe = None
        if margin_used and position.unrealized_pnl is not None:
            try:
                roe = (position.unrealized_pnl / margin_used) * 100.0
            except Exception:
                roe = None

        peak_roe = None
        if roe is not None:
            peak = peak_roe_tracker.get(symbol)
            if peak is None or roe > peak:
                peak_roe_tracker[symbol] = roe
                peak = roe
            peak_roe = peak

        stop_loss, take_profit = _extract_sl_tp(order_index.get(symbol, []))
        opened_at = position.opened_at
        held_for = _format_duration(opened_at)

        payload[symbol] = {
            "side": position.direction.lower() if position.direction else None,
            "margin_used": margin_used,
            "entry": position.entry_price,
            "leverage": position.leverage,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "pnl": position.unrealized_pnl,
            "roe": roe,
            "liquidation": position.liquidation_price,
            "held_for": held_for,
            "opened_at": opened_at.isoformat() if opened_at else None,
            "peak_roe": peak_roe,
        }

    return payload


def _days_left(goal_deadline: Optional[date]) -> Optional[int]:
    if not goal_deadline:
        return None
    today = datetime.now(timezone.utc).date()
    delta = (goal_deadline - today).days
    return max(delta, 0)


def _has_vegas_tunnels(defaults: Dict[str, Any]) -> bool:
    return any(
        defaults.get(flag) is True
        for flag in (
            "vegas_show_fast_tunnel",
            "vegas_show_medium_tunnel",
            "vegas_show_slow_tunnel",
        )
    )


def _resolve_ema_lengths(defaults: Dict[str, Any]) -> List[int]:
    lengths: List[int] = []
    raw_lengths = defaults.get("ema_lengths")
    if isinstance(raw_lengths, (list, tuple)):
        for raw in raw_lengths:
            try:
                value = int(raw)
            except (TypeError, ValueError):
                continue
            if value > 0 and value not in lengths:
                lengths.append(value)

    if not lengths:
        if defaults.get("vegas_show_fast_tunnel") is True:
            lengths.extend([36, 44])
        if defaults.get("vegas_show_medium_tunnel") is True:
            lengths.extend([144, 169])
        if defaults.get("vegas_show_slow_tunnel") is True:
            lengths.extend([576, 676])

    if not lengths:
        lengths = [20, 50]

    return lengths


def _resolve_ema_colors(defaults: Dict[str, Any], lengths: List[int]) -> List[str]:
    colors: List[str] = []
    raw_colors = defaults.get("ema_colors")
    if isinstance(raw_colors, (list, tuple)):
        for raw in raw_colors:
            if raw is None:
                continue
            color = str(raw).strip()
            if color:
                colors.append(color)

    if len(colors) >= len(lengths):
        return colors[: len(lengths)]

    for length in lengths[len(colors) :]:
        colors.append(_VEGAS_EMA_COLOR_MAP.get(int(length), _DEFAULT_EMA_COLOR))

    return colors


def _resolve_bb_length(defaults: Dict[str, Any]) -> int:
    raw = defaults.get("bb_length", defaults.get("vegas_bb_length", 20))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 20
    return max(1, value)


def _resolve_bb_std(defaults: Dict[str, Any]) -> float:
    raw = defaults.get("bb_std", defaults.get("vegas_bb_std", 2.0))
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 2.0
    return value if value > 0 else 2.0


def _resolve_candle_limit(
    interval: str,
    request_candles: Optional[int],
    defaults: Dict[str, Any],
) -> int:
    if isinstance(request_candles, int) and request_candles > 0:
        return request_candles

    interval_key = (interval or "").strip()
    interval_key_lower = interval_key.lower() if interval_key else ""
    vegas_configs = defaults.get("vegas_interval_configs")
    if interval_key and isinstance(vegas_configs, dict):
        raw = vegas_configs.get(interval_key)
        if raw is None and interval_key_lower:
            raw = vegas_configs.get(interval_key_lower)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = None
        if value and value > 0:
            return value

    chart_snapshot_interval = str(defaults.get("chart_snapshot_interval") or "").strip()
    chart2_interval = str(defaults.get("chart2_interval") or "").strip()
    chart_snapshot_lower = chart_snapshot_interval.lower()
    chart2_lower = chart2_interval.lower()
    if interval_key and interval_key in {chart_snapshot_interval, chart_snapshot_lower}:
        raw = defaults.get("chart1_candles")
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = None
        if value and value > 0:
            return value

    if defaults.get("chart2_enabled") and interval_key and interval_key in {chart2_interval, chart2_lower}:
        raw = defaults.get("chart2_candles")
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = None
        if value and value > 0:
            return value

    raw = defaults.get("candles")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = None
    if value and value > 0:
        return value

    return 50
