from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional


@dataclass(frozen=True)
class AutomationConfig:
    execution_mode: str
    ema_interval_seconds: int
    quant_interval_seconds: int
    pending_entry_timeout_seconds: int
    max_positions: int
    provider: Optional[str]
    model: Optional[str]
    auto_add_enabled: bool = False
    auto_add_trigger_atr_multiple: float = 1.0
    auto_add_tranche_margin_pct: float = 0.80
    auto_add_max_tranches: int = 3
    auto_add_protected_stop_roe: float = 0.002
    reasoning_effort: Optional[str] = None
    include_entry_timing_15m_chart: bool = False
    use_all_monitored_interval_charts: bool = False
    reverse_order_enabled: bool = False
    vegas_prompt_configs: Optional[Dict[str, int]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
