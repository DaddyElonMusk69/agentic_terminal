from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class PromptTemplate:
    id: int
    name: str
    intro: str
    response_format: str
    quant_fields: Optional[List[str]] = None
    chart_defaults: Optional[Dict[str, Any]] = None
    is_default: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass(frozen=True)
class ChartRequest:
    interval: str
    candles: Optional[int] = None
    overlays: Optional[List[str]] = None


@dataclass(frozen=True)
class PromptBuildRequest:
    request_id: str
    template_id: Optional[int]
    trigger_reason: str
    tickers: List[str]
    intervals: List[str]
    provider: Optional[str] = None
    chart_requests: List[ChartRequest] = field(default_factory=list)
    quant_fields: Optional[List[str]] = None
    template_context: Dict[str, Any] = field(default_factory=dict)
    quant_snapshot_id: Optional[str] = None
    trace_id: Optional[str] = None

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "PromptBuildRequest":
        raw_chart_requests = payload.get("chart_requests") or []
        chart_requests = [
            ChartRequest(
                interval=str(item.get("interval", "")).strip(),
                candles=item.get("candles"),
                overlays=item.get("overlays"),
            )
            for item in raw_chart_requests
            if isinstance(item, dict)
        ]
        return cls(
            request_id=str(payload.get("request_id", "")),
            template_id=payload.get("template_id"),
            trigger_reason=str(payload.get("trigger_reason", "")),
            tickers=[str(item) for item in payload.get("tickers") or []],
            intervals=[str(item) for item in payload.get("intervals") or []],
            provider=str(payload.get("provider")).strip() if payload.get("provider") else None,
            chart_requests=chart_requests,
            quant_fields=payload.get("quant_fields"),
            template_context=payload.get("template_context") or {},
            quant_snapshot_id=payload.get("quant_snapshot_id"),
            trace_id=payload.get("trace_id"),
        )


@dataclass(frozen=True)
class PromptBuildResult:
    request_id: str
    template_id: int
    template_name: str
    prompt_text: str
    data: Dict[str, Any]
    chart_items: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "template_id": self.template_id,
            "template_name": self.template_name,
            "prompt_text": self.prompt_text,
            "data": self.data,
            "chart_items": self.chart_items,
            "created_at": self.created_at.isoformat(),
        }
