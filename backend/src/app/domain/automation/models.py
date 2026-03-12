from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional


@dataclass(frozen=True)
class AutomationConfig:
    execution_mode: str
    ema_interval_seconds: int
    quant_interval_seconds: int
    provider: Optional[str]
    model: Optional[str]
    include_entry_timing_15m_chart: bool = False
    reverse_order_enabled: bool = False
    vegas_prompt_configs: Optional[Dict[str, int]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
