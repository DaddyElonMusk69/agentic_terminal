from datetime import datetime, timezone
from typing import Any, Dict, Optional


def build_envelope(
    topic: str,
    payload: Dict[str, Any],
    message_type: str = "event",
    request_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    envelope: Dict[str, Any] = {
        "v": 1,
        "type": message_type,
        "topic": topic,
        "payload": payload,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    if request_id:
        envelope["request_id"] = request_id
    if trace_id:
        envelope["trace_id"] = trace_id
    return envelope
