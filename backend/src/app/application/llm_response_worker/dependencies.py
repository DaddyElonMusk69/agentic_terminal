from functools import lru_cache

from app.application.llm_response_worker.service import LlmResponseWorker


@lru_cache(maxsize=1)
def get_llm_response_worker_service() -> LlmResponseWorker:
    return LlmResponseWorker()
