from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class LlmCallRequest:
    prompt_text: str
    images: List[Dict[str, Any]]
    model: str
    temperature: float
    max_tokens: Optional[int] = None


@dataclass(frozen=True)
class LlmCallResponse:
    content: str
    model: str
    tokens_used: int
    latency_ms: float
    raw_response: Optional[Dict[str, Any]] = None
    created_at: datetime = _utcnow()
