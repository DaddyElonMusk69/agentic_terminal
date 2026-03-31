from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Set


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EmaStateTrigger(Enum):
    NEW_RESONANCE = "new_resonance"
    RESONANCE_INCREASE = "resonance_increase"
    STRUCTURE_SHIFT = "structure_shift"
    RESONANCE_REFRESH = "resonance_refresh"
    BB_REJECTION_ENTRY = "bb_rejection_entry"
    POSITION_MANAGEMENT = "position_management"
    BB_EXIT_WARNING = "bb_exit_warning"
    NONE = "none"


class EmaTickerPhase(Enum):
    IDLE = "idle"
    ANALYZING = "analyzing"
    PENDING_ENTRY = "pending_entry"
    IN_POSITION = "in_position"


@dataclass(frozen=True)
class EmaStateManagerConfig:
    min_resonance: int
    ema_resonance_cooldown_seconds: int
    bb_rejection_cooldown_seconds: int
    bb_exit_warning_cooldown_seconds: int
    position_check_interval_seconds: int
    bb_rejection_min_touches: int
    bb_htf_min_interval_minutes: int
    new_resonance_min_touches: int
    emit_new_resonance: bool = True
    emit_resonance_increase: bool = True
    emit_structure_shift: bool = True
    emit_resonance_refresh: bool = True
    emit_bb_rejection_upper: bool = True
    emit_bb_rejection_lower: bool = True
    emit_position_management: bool = True
    emit_bb_exit_warning: bool = True


@dataclass(frozen=True)
class PositionSnapshot:
    symbol: str
    direction: str
    entry_price: float | None = None


@dataclass(frozen=True)
class PendingEntrySnapshot:
    symbol: str
    side: str
    limit_price: float
    placed_at: datetime
    expires_at: datetime
    order_id: str | None = None


@dataclass
class IntervalSignalCounts:
    interval: str
    ema_signals: int = 0
    bb_upper_signals: int = 0
    bb_lower_signals: int = 0
    last_updated: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> Dict:
        return {
            "interval": self.interval,
            "ema_signals": self.ema_signals,
            "bb_upper_signals": self.bb_upper_signals,
            "bb_lower_signals": self.bb_lower_signals,
            "last_updated": self.last_updated.isoformat(),
        }


@dataclass
class EmaTickerState:
    symbol: str
    phase: EmaTickerPhase = EmaTickerPhase.IDLE
    resonance_count: int = 0
    active_intervals: Set[str] = field(default_factory=set)
    interval_states: Dict[str, IntervalSignalCounts] = field(default_factory=dict)

    position_direction: Optional[str] = None
    position_entry_price: Optional[float] = None
    position_opened_at: Optional[datetime] = None
    pending_entry_side: Optional[str] = None
    pending_entry_limit_price: Optional[float] = None
    pending_entry_expires_at: Optional[datetime] = None

    bb_upper_touch_count: int = 0
    bb_lower_touch_count: int = 0
    bb_rejection_direction: Optional[str] = None
    new_resonance_touch_count: int = 0

    last_position_prompt_at: Optional[datetime] = None
    last_ema_resonance_prompt_at: Optional[datetime] = None
    last_bb_rejection_prompt_at: Optional[datetime] = None
    last_bb_exit_warning_prompt_at: Optional[datetime] = None

    last_trigger: EmaStateTrigger = EmaStateTrigger.NONE
    last_trigger_at: Optional[datetime] = None
    last_updated: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "phase": self.phase.value,
            "resonance_count": self.resonance_count,
            "active_intervals": sorted(self.active_intervals),
            "interval_states": {
                key: value.to_dict() for key, value in self.interval_states.items()
            },
            "position_direction": self.position_direction,
            "position_entry_price": self.position_entry_price,
            "position_opened_at": self.position_opened_at.isoformat() if self.position_opened_at else None,
            "pending_entry_side": self.pending_entry_side,
            "pending_entry_limit_price": self.pending_entry_limit_price,
            "pending_entry_expires_at": self.pending_entry_expires_at.isoformat()
            if self.pending_entry_expires_at
            else None,
            "bb_upper_touch_count": self.bb_upper_touch_count,
            "bb_lower_touch_count": self.bb_lower_touch_count,
            "bb_rejection_direction": self.bb_rejection_direction,
            "new_resonance_touch_count": self.new_resonance_touch_count,
            "last_position_prompt_at": self.last_position_prompt_at.isoformat() if self.last_position_prompt_at else None,
            "last_ema_resonance_prompt_at": self.last_ema_resonance_prompt_at.isoformat()
            if self.last_ema_resonance_prompt_at
            else None,
            "last_bb_rejection_prompt_at": self.last_bb_rejection_prompt_at.isoformat()
            if self.last_bb_rejection_prompt_at
            else None,
            "last_bb_exit_warning_prompt_at": self.last_bb_exit_warning_prompt_at.isoformat()
            if self.last_bb_exit_warning_prompt_at
            else None,
            "last_trigger": self.last_trigger.value,
            "last_trigger_at": self.last_trigger_at.isoformat() if self.last_trigger_at else None,
            "last_updated": self.last_updated.isoformat(),
        }


@dataclass
class EmaStateEvent:
    symbol: str
    trigger_reason: EmaStateTrigger
    ticker_state: EmaTickerState
    resonance_count: int = 0
    active_intervals: List[str] = field(default_factory=list)
    direction_signal: Optional[str] = None
    bb_signal_intervals: List[str] = field(default_factory=list)
    previous_resonance: int = 0
    previous_intervals: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "trigger_reason": self.trigger_reason.value,
            "resonance_count": self.resonance_count,
            "active_intervals": self.active_intervals,
            "direction_signal": self.direction_signal,
            "bb_signal_intervals": self.bb_signal_intervals,
            "previous_resonance": self.previous_resonance,
            "previous_intervals": self.previous_intervals,
            "timestamp": self.timestamp.isoformat(),
        }


DEFAULT_EMA_STATE_MANAGER_CONFIG = EmaStateManagerConfig(
    min_resonance=2,
    ema_resonance_cooldown_seconds=600,
    bb_rejection_cooldown_seconds=1200,
    bb_exit_warning_cooldown_seconds=600,
    position_check_interval_seconds=1800,
    bb_rejection_min_touches=10,
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
