from functools import lru_cache

from app.application.prompt_templates.service import PromptTemplateService
from app.infrastructure.db import get_sessionmaker
from app.infrastructure.repositories.prompt_template_repository import SqlPromptTemplateRepository


@lru_cache(maxsize=1)
def get_prompt_template_service() -> PromptTemplateService:
    repository = SqlPromptTemplateRepository(get_sessionmaker())
    return PromptTemplateService(repository)
