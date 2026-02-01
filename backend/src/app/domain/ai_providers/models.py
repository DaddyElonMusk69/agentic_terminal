from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    api_key: Optional[str]
    default_model: Optional[str]
    is_enabled: bool
    settings: Optional[Dict[str, str]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    models: List[str]
    configured: bool
    is_enabled: bool
    default_model: Optional[str]
    settings: Optional[Dict[str, str]] = None


@dataclass(frozen=True)
class ProviderValidationResult:
    provider: str
    model: str
    latency_ms: float
    valid: bool = True
