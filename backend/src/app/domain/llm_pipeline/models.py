from dataclasses import dataclass
from typing import Dict

from app.domain.llm_caller.models import LlmCallResponse
from app.domain.llm_response_worker.models import LlmResponseParseResult


@dataclass(frozen=True)
class LlmExecutionResult:
    call_response: LlmCallResponse
    parse_result: LlmResponseParseResult

    def to_dict(self) -> Dict:
        return {
            "call_response": {
                "content": self.call_response.content,
                "model": self.call_response.model,
                "tokens_used": self.call_response.tokens_used,
                "latency_ms": self.call_response.latency_ms,
            },
            "parse_result": self.parse_result.to_dict(),
        }
