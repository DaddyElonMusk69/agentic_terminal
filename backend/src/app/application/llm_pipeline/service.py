from app.application.llm_caller.service import LlmCallerService
from app.application.llm_response_worker.service import LlmResponseWorker
from app.domain.llm_caller.models import LlmCallRequest
from app.domain.llm_pipeline.models import LlmExecutionResult


class LlmExecutionService:
    def __init__(self, caller: LlmCallerService, response_worker: LlmResponseWorker) -> None:
        self._caller = caller
        self._response_worker = response_worker

    async def execute(
        self,
        request: LlmCallRequest,
        api_key: str | None = None,
        base_url: str | None = None,
        protocol: str | None = None,
        provider: str | None = None,
    ) -> LlmExecutionResult:
        call_response = await self._caller.call(
            request,
            api_key=api_key,
            base_url=base_url,
            protocol=protocol,
            provider=provider,
        )
        parse_result = self._response_worker.parse(call_response.content)
        return LlmExecutionResult(call_response=call_response, parse_result=parse_result)
