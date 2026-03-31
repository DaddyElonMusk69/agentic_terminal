from __future__ import annotations

from datetime import datetime, timezone

import pytest

import app.application.automation.topics as topics
from app.application.automation.pipeline import AutomationPipelineService
from app.domain.ema_scanner.models import EmaScannerConfig, EmaScannerSignal
from app.domain.ema_state_manager.models import (
    DEFAULT_EMA_STATE_MANAGER_CONFIG,
    EmaStateEvent,
    EmaStateTrigger,
    EmaTickerState,
)


def _ema_signal(symbol: str, timeframe: str) -> EmaScannerSignal:
    return EmaScannerSignal(
        symbol=symbol,
        timeframe=timeframe,
        indicator="EMA",
        parameter="EMA-144",
        value=100.0,
        price=101.0,
        lower_bound=99.0,
        upper_bound=102.0,
        condition="proximity",
        timestamp=datetime.now(timezone.utc),
    )


def _event(symbol: str) -> EmaStateEvent:
    return EmaStateEvent(
        symbol=symbol,
        trigger_reason=EmaStateTrigger.NEW_RESONANCE,
        ticker_state=EmaTickerState(symbol=symbol),
        resonance_count=2,
        active_intervals=["2h", "4h"],
        timestamp=datetime.now(timezone.utc),
    )


class StubEmaScanner:
    async def scan(
        self,
        config,
        log_callback=None,
        chart_store=None,
        asset_callback=None,
    ):
        del log_callback
        btc_signal = _ema_signal("BTC/USDT", "2h")
        eth_signal = _ema_signal("ETH/USDT", "4h")
        chart_store.setdefault("BTC/USDT", {})["2h"] = {"candles": []}
        chart_store.setdefault("ETH/USDT", {})["4h"] = {"candles": []}
        await asset_callback("BTC/USDT", [btc_signal], chart_store["BTC/USDT"])
        await asset_callback("ETH/USDT", [eth_signal], chart_store["ETH/USDT"])
        return [btc_signal, eth_signal]


class StubEmaConfig:
    async def build_config(self, log_callback=None) -> EmaScannerConfig:
        del log_callback
        return EmaScannerConfig(
            assets=["BTC", "ETH"],
            timeframes=["2h", "4h"],
            ema_lengths=[144],
            tolerance_pct=0.5,
        )


class StubEmaStateManager:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def process_signals(
        self,
        signals,
        monitored_assets,
        quote_asset="USDT",
        open_positions=None,
        pending_entries=None,
        update_assets=None,
        prune_missing=True,
        state_config=None,
    ):
        self.calls.append(
            {
                "signals": list(signals),
                "monitored_assets": list(monitored_assets),
                "quote_asset": quote_asset,
                "open_positions": list(open_positions or []),
                "pending_entries": list(pending_entries or []),
                "update_assets": list(update_assets) if update_assets is not None else None,
                "prune_missing": prune_missing,
                "state_config": state_config,
            }
        )
        if update_assets == []:
            return []
        if not update_assets:
            return []
        return [_event(update_assets[0])]

    async def get_config(self):
        return DEFAULT_EMA_STATE_MANAGER_CONFIG

    def get_all_states(self):
        return {}


class StubQuantScanner:
    pass


class StubQuantConfig:
    pass


class StubPromptQueue:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    async def enqueue(self, payload: dict) -> None:
        self.payloads.append(dict(payload))


class StubOutbox:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def enqueue_event(self, topic: str, payload: dict) -> None:
        self.events.append((topic, dict(payload)))


class _PortfolioSnapshot:
    positions = []


class StubPortfolio:
    async def get_portfolio_snapshot(self):
        return _PortfolioSnapshot()

    async def get_recent_trades(self, limit: int):  # pragma: no cover - production only
        del limit
        return []


@pytest.mark.asyncio
async def test_pipeline_enqueues_prompts_progressively(monkeypatch):
    def _fake_prompt_payload(event, timeframes, **kwargs):
        del kwargs
        return {
            "symbol": event.symbol,
            "trigger_reason": event.trigger_reason.value,
            "timeframes": list(timeframes),
        }

    monkeypatch.setattr(
        "app.application.automation.pipeline.build_prompt_request",
        _fake_prompt_payload,
    )

    state_manager = StubEmaStateManager()
    prompt_queue = StubPromptQueue()
    outbox = StubOutbox()
    pipeline = AutomationPipelineService(
        ema_scanner=StubEmaScanner(),
        ema_config=StubEmaConfig(),
        ema_state_manager=state_manager,
        quant_scanner=StubQuantScanner(),
        quant_config=StubQuantConfig(),
        prompt_queue=prompt_queue,
        outbox=outbox,
        portfolio_service=StubPortfolio(),
        telegram_notifier=None,
        history_service=None,
    )

    result = await pipeline.run_ema_cycle()

    assert result["signals"] == 2
    assert result["events"] == 2
    assert result["queued"] == 2
    assert len(prompt_queue.payloads) == 2

    # Two incremental per-asset updates + one prune pass.
    assert len(state_manager.calls) == 3
    assert state_manager.calls[0]["update_assets"] == ["BTC/USDT"]
    assert state_manager.calls[0]["prune_missing"] is False
    assert state_manager.calls[1]["update_assets"] == ["ETH/USDT"]
    assert state_manager.calls[1]["prune_missing"] is False
    assert state_manager.calls[2]["update_assets"] == []
    assert state_manager.calls[2]["prune_missing"] is True

    topics_seen = [topic for topic, _ in outbox.events]
    prompt_idx = topics_seen.index(topics.PROMPT_REQUESTED)
    ema_signals_idx = topics_seen.index(topics.EMA_SIGNALS)
    assert prompt_idx < ema_signals_idx
