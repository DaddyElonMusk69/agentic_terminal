from datetime import datetime, timezone

from app.domain.ema_scanner.models import EmaScannerSignal
from app.domain.ema_state_manager.models import (
    EmaStateManagerConfig,
    EmaStateTrigger,
    EmaTickerPhase,
    PendingEntrySnapshot,
    PositionSnapshot,
)
from app.domain.ema_state_manager.service import EmaStateManager


def _config() -> EmaStateManagerConfig:
    return EmaStateManagerConfig(
        min_resonance=2,
        ema_resonance_cooldown_seconds=60,
        bb_rejection_cooldown_seconds=60,
        bb_exit_warning_cooldown_seconds=60,
        position_check_interval_seconds=60,
        bb_rejection_min_touches=2,
        bb_htf_min_interval_minutes=480,
        new_resonance_min_touches=1,
        emit_new_resonance=True,
        emit_resonance_increase=True,
        emit_structure_shift=True,
        emit_resonance_refresh=True,
        emit_bb_rejection_upper=True,
        emit_bb_rejection_lower=True,
        emit_position_management=True,
        emit_bb_exit_warning=True,
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


def _bb_signal(symbol: str, timeframe: str, parameter: str) -> EmaScannerSignal:
    return EmaScannerSignal(
        symbol=symbol,
        timeframe=timeframe,
        indicator="BB",
        parameter=parameter,
        value=100.0,
        price=101.0,
        lower_bound=99.0,
        upper_bound=102.0,
        condition="proximity",
        timestamp=datetime.now(timezone.utc),
    )


def test_state_manager_emits_new_resonance():
    manager = EmaStateManager()
    config = _config()

    signals = [
        _ema_signal("BTC/USDT", "2h"),
        _ema_signal("BTC/USDT", "4h"),
    ]

    events = manager.update(signals, monitored_symbols=["BTC/USDT"], config=config)

    assert len(events) == 1
    event = events[0]
    assert event.trigger_reason == EmaStateTrigger.NEW_RESONANCE
    assert set(event.active_intervals) == {"2h", "4h"}


def test_state_manager_bb_rejection_entry_requires_consecutive_touches():
    manager = EmaStateManager()
    config = _config()

    signals = [_bb_signal("BTC/USDT", "8h", "BB-Upper")]

    events = manager.update(signals, monitored_symbols=["BTC/USDT"], config=config)
    assert events == []

    events = manager.update(signals, monitored_symbols=["BTC/USDT"], config=config)
    assert len(events) == 1
    event = events[0]
    assert event.trigger_reason == EmaStateTrigger.BB_REJECTION_ENTRY
    assert event.direction_signal == "SHORT"
    assert event.bb_signal_intervals == ["8h"]


def test_state_manager_ignores_unmonitored_symbols():
    manager = EmaStateManager()
    config = _config()

    signals = [_ema_signal("ETH/USDT", "4h"), _ema_signal("ETH/USDT", "8h")]

    events = manager.update(signals, monitored_symbols=["BTC/USDT"], config=config)
    assert events == []
    assert manager.get_state("ETH/USDT") is None


def test_state_manager_prunes_removed_symbols():
    manager = EmaStateManager()
    config = _config()

    signals = [_ema_signal("BTC/USDT", "4h"), _ema_signal("BTC/USDT", "8h")]
    manager.update(signals, monitored_symbols=["BTC/USDT"], config=config)
    assert manager.get_state("BTC/USDT") is not None

    manager.update([], monitored_symbols=["ETH/USDT"], config=config)
    assert manager.get_state("BTC/USDT") is None


def test_state_manager_new_resonance_requires_consecutive_touches():
    manager = EmaStateManager()
    config = EmaStateManagerConfig(
        min_resonance=2,
        ema_resonance_cooldown_seconds=60,
        bb_rejection_cooldown_seconds=60,
        bb_exit_warning_cooldown_seconds=60,
        position_check_interval_seconds=60,
        bb_rejection_min_touches=2,
        bb_htf_min_interval_minutes=480,
        new_resonance_min_touches=3,
        emit_new_resonance=True,
        emit_resonance_increase=True,
        emit_structure_shift=True,
        emit_resonance_refresh=True,
        emit_bb_rejection_upper=True,
        emit_bb_rejection_lower=True,
        emit_position_management=True,
        emit_bb_exit_warning=True,
    )

    signals = [_ema_signal("BTC/USDT", "2h"), _ema_signal("BTC/USDT", "4h")]

    # First two updates should not emit (need 3 touches)
    events = manager.update(signals, monitored_symbols=["BTC/USDT"], config=config)
    assert events == []
    events = manager.update(signals, monitored_symbols=["BTC/USDT"], config=config)
    assert events == []

    # Third update should emit NEW_RESONANCE
    events = manager.update(signals, monitored_symbols=["BTC/USDT"], config=config)
    assert len(events) == 1
    assert events[0].trigger_reason == EmaStateTrigger.NEW_RESONANCE


def test_state_manager_partial_update_does_not_prune_other_symbols():
    manager = EmaStateManager()
    config = _config()

    btc_signals = [_ema_signal("BTC/USDT", "2h"), _ema_signal("BTC/USDT", "4h")]
    eth_signals = [_ema_signal("ETH/USDT", "2h"), _ema_signal("ETH/USDT", "4h")]

    manager.update(
        btc_signals,
        monitored_symbols=["BTC/USDT", "ETH/USDT"],
        config=config,
        update_symbols=["BTC/USDT"],
        prune_missing=False,
    )
    assert manager.get_state("BTC/USDT") is not None
    assert manager.get_state("ETH/USDT") is None

    events = manager.update(
        eth_signals,
        monitored_symbols=["BTC/USDT", "ETH/USDT"],
        config=config,
        update_symbols=["ETH/USDT"],
        prune_missing=False,
    )
    assert len(events) == 1
    assert events[0].symbol == "ETH/USDT"
    assert manager.get_state("BTC/USDT") is not None
    assert manager.get_state("ETH/USDT") is not None


def test_state_manager_partial_update_with_prune_removes_missing_symbols():
    manager = EmaStateManager()
    config = _config()

    signals = [_ema_signal("BTC/USDT", "4h"), _ema_signal("BTC/USDT", "8h")]
    manager.update(signals, monitored_symbols=["BTC/USDT"], config=config)
    assert manager.get_state("BTC/USDT") is not None

    manager.update(
        [],
        monitored_symbols=["ETH/USDT"],
        config=config,
        update_symbols=[],
        prune_missing=True,
    )
    assert manager.get_state("BTC/USDT") is None


def test_state_manager_marks_symbol_as_pending_entry_and_suppresses_events():
    manager = EmaStateManager()
    config = _config()

    pending_entry = PendingEntrySnapshot(
        symbol="BTC/USDT",
        side="LONG",
        limit_price=100.0,
        placed_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc),
        order_id="ord-1",
    )

    events = manager.update(
        [],
        monitored_symbols=["BTC/USDT"],
        config=config,
        pending_entries=[pending_entry],
    )

    assert events == []
    state = manager.get_state("BTC/USDT")
    assert state is not None
    assert state.phase == EmaTickerPhase.PENDING_ENTRY
    assert state.pending_entry_side == "LONG"


def test_state_manager_suppresses_entry_events_when_max_positions_reached():
    manager = EmaStateManager()
    config = _config()
    signals = [_ema_signal("BTC/USDT", "2h"), _ema_signal("BTC/USDT", "4h")]

    open_positions = [
        PositionSnapshot(symbol="ETH/USDT", direction="LONG", entry_price=100.0),
        PositionSnapshot(symbol="SOL/USDT", direction="SHORT", entry_price=100.0),
    ]

    events = manager.update(
        signals,
        monitored_symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT"],
        config=config,
        open_positions=open_positions,
        max_open_positions=2,
    )

    assert events == []
    state = manager.get_state("BTC/USDT")
    assert state is not None
    assert state.phase == EmaTickerPhase.ANALYZING


def test_state_manager_allows_position_management_events_when_max_positions_reached():
    manager = EmaStateManager()
    config = EmaStateManagerConfig(
        min_resonance=2,
        ema_resonance_cooldown_seconds=60,
        bb_rejection_cooldown_seconds=60,
        bb_exit_warning_cooldown_seconds=60,
        position_check_interval_seconds=0,
        bb_rejection_min_touches=2,
        bb_htf_min_interval_minutes=480,
        new_resonance_min_touches=1,
        emit_new_resonance=True,
        emit_resonance_increase=True,
        emit_structure_shift=True,
        emit_resonance_refresh=True,
        emit_bb_rejection_upper=True,
        emit_bb_rejection_lower=True,
        emit_position_management=True,
        emit_bb_exit_warning=True,
    )

    open_positions = [PositionSnapshot(symbol="BTC/USDT", direction="LONG", entry_price=100.0)]

    first = manager.update(
        [],
        monitored_symbols=["BTC/USDT"],
        config=config,
        open_positions=open_positions,
        max_open_positions=1,
    )
    assert first == []

    second = manager.update(
        [],
        monitored_symbols=["BTC/USDT"],
        config=config,
        open_positions=open_positions,
        max_open_positions=1,
    )
    assert len(second) == 1
    assert second[0].trigger_reason == EmaStateTrigger.POSITION_MANAGEMENT
