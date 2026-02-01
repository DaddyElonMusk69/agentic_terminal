from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable, Sequence

from app.application.telegram.config_service import TelegramConfigService
from app.application.telegram.message_service import TelegramMessageService
from app.domain.ema_scanner.models import EmaScannerSignal
from app.domain.ema_state_manager.models import EmaStateEvent, EmaStateTrigger


logger = logging.getLogger(__name__)


class TelegramNotificationService:
    def __init__(
        self,
        config_service: TelegramConfigService,
        message_service: TelegramMessageService,
    ) -> None:
        self._config_service = config_service
        self._message_service = message_service

    async def notify_ema_event(
        self,
        event: EmaStateEvent,
        signals: Sequence[EmaScannerSignal] | None = None,
    ) -> None:
        try:
            config = await self._config_service.get_config()
            if not config.enabled or not config.notifications.ema_automation:
                return
            if event.trigger_reason not in (
                EmaStateTrigger.NEW_RESONANCE,
                EmaStateTrigger.BB_REJECTION_ENTRY,
            ):
                return

            message = _format_ema_notification(event, signals or ())
            result = await self._message_service.send_message(
                message,
                parse_mode="Markdown",
            )
            if not result.sent:
                logger.info("Telegram EMA notification not sent: %s", result.error)
        except Exception as exc:  # pragma: no cover - best-effort delivery
            logger.warning("Telegram EMA notification failed: %s", exc)

    async def notify_llm_considerations(
        self,
        considerations: Sequence[dict],
        cycle_number: int | None = None,
        session_id: str | None = None,
    ) -> None:
        if not considerations:
            return
        try:
            config = await self._config_service.get_config()
            if not config.enabled or not config.notifications.llm_considerations:
                return

            message = _format_considerations_message(
                considerations,
                cycle_number=cycle_number,
                session_id=session_id,
            )
            result = await self._message_service.send_message(
                message,
                parse_mode="",
            )
            if not result.sent:
                logger.info("Telegram considerations not sent: %s", result.error)
        except Exception as exc:  # pragma: no cover - best-effort delivery
            logger.warning("Telegram considerations failed: %s", exc)


def _format_ema_notification(
    event: EmaStateEvent,
    signals: Iterable[EmaScannerSignal],
) -> str:
    trigger_name = event.trigger_reason.value.replace("_", " ").title()
    intervals = ", ".join(sorted(event.active_intervals)) if event.active_intervals else "n/a"
    direction = (event.direction_signal or "").upper()

    lines = [
        "*EMA Scanner Alert*",
        "",
        f"*Ticker:* `{event.symbol}`",
        f"*Trigger:* {trigger_name}",
        f"*Resonance:* {event.resonance_count} intervals",
        f"*Intervals:* {intervals}",
    ]

    if direction:
        lines.append(f"*Direction:* {direction}")

    symbol_signals = [signal for signal in signals if signal.symbol == event.symbol]

    ema_lines = _format_signal_block(symbol_signals, indicator="EMA")
    if ema_lines:
        lines.append("")
        lines.append("*EMA Signals*")
        lines.extend(ema_lines)

    bb_lines = _format_signal_block(symbol_signals, indicator="BB")
    if bb_lines:
        lines.append("")
        lines.append("*BB Signals*")
        lines.extend(bb_lines)

    context = _trigger_context_line(event.trigger_reason, direction)
    if context:
        lines.append("")
        lines.append(f"_{context}_")

    timestamp = event.timestamp.astimezone(timezone.utc).strftime("%H:%M:%S UTC")
    lines.append("")
    lines.append(f"_{timestamp}_")
    return "\n".join(lines)


def _format_signal_block(
    signals: Iterable[EmaScannerSignal],
    indicator: str,
) -> list[str]:
    indicator = indicator.upper()
    grouped: dict[str, list[EmaScannerSignal]] = {}
    for signal in signals:
        if signal.indicator.upper() != indicator:
            continue
        grouped.setdefault(signal.timeframe, []).append(signal)

    lines: list[str] = []
    for timeframe in sorted(grouped.keys()):
        items = grouped[timeframe][:2]
        formatted = []
        for item in items:
            if indicator == "EMA":
                formatted.append(
                    f"{item.parameter} (${_fmt(item.price)} ~ ${_fmt(item.value)})"
                )
            else:
                formatted.append(
                    f"{item.parameter} (${_fmt(item.price)} vs ${_fmt(item.value)}, {item.condition})"
                )
        lines.append(f"- {timeframe}: {', '.join(formatted)}")
    return lines


def _fmt(value: float) -> str:
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "n/a"


def _trigger_context_line(trigger: EmaStateTrigger, direction: str) -> str:
    if trigger == EmaStateTrigger.NEW_RESONANCE:
        return "New multi-timeframe alignment detected. Potential entry opportunity."
    if trigger == EmaStateTrigger.BB_REJECTION_ENTRY:
        if direction == "LONG":
            return "Price touching BB lower band. Potential mean reversion long."
        if direction == "SHORT":
            return "Price touching BB upper band. Potential mean reversion short."
        return "Price touching BB band. Potential mean reversion entry."
    return ""


def _format_considerations_message(
    considerations: Sequence[dict],
    cycle_number: int | None,
    session_id: str | None,
) -> str:
    lines = ["Automation AI Watchlist", ""]

    if cycle_number:
        lines.append(f"Cycle #{cycle_number}")
        lines.append("")

    lines.append("=== Market Outlook ===")
    lines.append("")

    for item in considerations:
        symbol = str(item.get("symbol") or item.get("asset") or "Unknown").strip().upper()
        action = str(item.get("recommend_action") or item.get("action") or "HOLD").strip().upper()
        lines.append(f"- {symbol} - {action}")

        reasoning = str(item.get("reasoning") or "").strip()
        if reasoning:
            max_len = 200
            if len(reasoning) > max_len:
                reasoning = reasoning[:max_len].rstrip() + "..."
            lines.append(f"  {reasoning}")

        lines.append("")

    timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    lines.append(timestamp)
    return "\n".join(lines)
