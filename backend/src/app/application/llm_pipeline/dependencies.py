from functools import lru_cache

from app.application.llm_caller.dependencies import get_llm_caller_service
from app.application.llm_pipeline.service import LlmExecutionService
from app.application.llm_response_worker.dependencies import get_llm_response_worker_service


@lru_cache(maxsize=1)
def get_llm_execution_service() -> LlmExecutionService:
    return LlmExecutionService(
        caller=get_llm_caller_service(),
        response_worker=get_llm_response_worker_service(),
    )
