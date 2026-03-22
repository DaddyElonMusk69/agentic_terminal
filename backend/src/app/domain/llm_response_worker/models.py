from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ExecutionAction(Enum):
    OPEN_LONG = "OPEN_LONG"
    OPEN_SHORT = "OPEN_SHORT"
    OPEN_LONG_LIMIT = "OPEN_LONG_LIMIT"
    OPEN_SHORT_LIMIT = "OPEN_SHORT_LIMIT"
    CLOSE = "CLOSE"
    REDUCE = "REDUCE"
    HOLD = "HOLD"
    UPDATE_SL = "UPDATE_SL"
    UPDATE_TP = "UPDATE_TP"
    CANCEL_SL = "CANCEL_SL"
    CANCEL_TP = "CANCEL_TP"
    CANCEL_SL_TP = "CANCEL_SL_TP"


@dataclass(frozen=True)
class ExecutionIdea:
    action: ExecutionAction
    symbol: str
    position_size_usd: Optional[float] = None
    entry_price: Optional[float] = None
    limit_price: Optional[float] = None
    time_in_force: Optional[str] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    new_stop_loss: Optional[float] = None
    new_take_profit: Optional[float] = None
    reduce_pct: Optional[float] = None
    confidence: Optional[float] = None
    reasoning: str = ""
    execute: bool = True
    leverage: Optional[int] = None
    tier: Optional[int] = None
    position_pct: Optional[float] = None
    stop_loss_roe: Optional[float] = None
    take_profit_roe: Optional[float] = None
    anchor_frame: Optional[str] = None
    active_tunnel: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "action": self.action.value,
            "symbol": self.symbol,
            "position_size_usd": self.position_size_usd,
            "entry_price": self.entry_price,
            "limit_price": self.limit_price,
            "time_in_force": self.time_in_force,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "new_stop_loss": self.new_stop_loss,
            "new_take_profit": self.new_take_profit,
            "reduce_pct": self.reduce_pct,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "execute": self.execute,
            "leverage": self.leverage,
            "tier": self.tier,
            "position_pct": self.position_pct,
            "stop_loss_roe": self.stop_loss_roe,
            "take_profit_roe": self.take_profit_roe,
            "anchor_frame": self.anchor_frame,
            "active_tunnel": self.active_tunnel,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ExecutionIdea":
        action_raw = payload.get("action")
        symbol_raw = payload.get("symbol")
        if not action_raw or not symbol_raw:
            raise ValueError("execution idea requires action and symbol")

        action = ExecutionAction(str(action_raw).upper())
        symbol = str(symbol_raw).upper()

        return cls(
            action=action,
            symbol=symbol,
            position_size_usd=_safe_float(payload.get("position_size_usd")),
            entry_price=_safe_float(payload.get("entry_price")),
            limit_price=_safe_float(payload.get("limit_price")),
            time_in_force=_safe_str(payload.get("time_in_force")),
            stop_loss=_safe_float(payload.get("stop_loss")),
            take_profit=_safe_float(payload.get("take_profit")),
            new_stop_loss=_safe_float(payload.get("new_stop_loss")),
            new_take_profit=_safe_float(payload.get("new_take_profit")),
            reduce_pct=_safe_float(payload.get("reduce_pct")),
            confidence=_safe_float(payload.get("confidence")),
            reasoning=_safe_str(payload.get("reasoning")) or "",
            execute=bool(payload.get("execute", True)),
            leverage=_safe_int(payload.get("leverage")),
            tier=_safe_int(payload.get("tier")),
            position_pct=_safe_float(payload.get("position_pct")),
            stop_loss_roe=_safe_float(payload.get("stop_loss_roe")),
            take_profit_roe=_safe_float(payload.get("take_profit_roe")),
            anchor_frame=_safe_trimmed_str(payload.get("anchor_frame")),
            active_tunnel=_safe_active_tunnel(payload.get("active_tunnel")),
        )


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _safe_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def _safe_trimmed_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _safe_active_tunnel(value: Any) -> Optional[str]:
    if isinstance(value, list):
        for item in value:
            normalized = _safe_trimmed_str(item)
            if normalized:
                return normalized
        return None
    return _safe_trimmed_str(value)


@dataclass(frozen=True)
class LlmResponseParseResult:
    success: bool
    ideas: List[ExecutionIdea] = field(default_factory=list)
    considerations: List[Dict] = field(default_factory=list)
    error: Optional[str] = None
    raw_response: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "ideas": [idea.to_dict() for idea in self.ideas],
            "considerations": self.considerations,
            "error": self.error,
            "raw_response": self.raw_response,
        }
