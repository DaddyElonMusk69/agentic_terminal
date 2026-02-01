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
    vegas_prompt_configs: Optional[Dict[str, int]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
