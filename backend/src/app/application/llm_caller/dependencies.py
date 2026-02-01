from functools import lru_cache

from app.application.llm_caller.service import LlmCallerService
from app.settings import get_settings


@lru_cache(maxsize=1)
def get_llm_caller_service() -> LlmCallerService:
    settings = get_settings()
    return LlmCallerService(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )
