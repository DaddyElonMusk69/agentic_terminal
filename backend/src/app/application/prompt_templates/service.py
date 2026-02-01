from __future__ import annotations

from typing import List, Optional

from sqlalchemy.exc import IntegrityError

from app.domain.prompt_builder.interfaces import PromptTemplateRepository
from app.domain.prompt_builder.models import PromptTemplate


class PromptTemplateService:
    def __init__(self, repository: PromptTemplateRepository) -> None:
        self._repository = repository

    async def list_templates(self) -> List[PromptTemplate]:
        return await self._repository.list_all()

    async def get_template(self, template_id: int) -> Optional[PromptTemplate]:
        return await self._repository.get_by_id(template_id)

    async def create_template(
        self,
        name: str,
        intro: str,
        response_format: str,
        quant_fields: Optional[List[str]],
        chart_defaults: Optional[dict],
        is_default: bool = False,
    ) -> PromptTemplate:
        try:
            template = await self._repository.create(
                name=name,
                intro=intro,
                response_format=response_format,
                quant_fields=quant_fields,
                chart_defaults=chart_defaults,
                is_default=is_default,
            )
        except IntegrityError as exc:
            raise ValueError("Template name already exists") from exc

        if is_default:
            await self._repository.set_default(template.id)
            template = await self._repository.get_by_id(template.id) or template
        return template

    async def update_template(self, template_id: int, fields: dict) -> PromptTemplate:
        if not fields:
            template = await self._repository.get_by_id(template_id)
            if template is None:
                raise ValueError("Template not found")
            return template

        make_default = fields.get("is_default") is True
        try:
            template = await self._repository.update(template_id, fields)
        except IntegrityError as exc:
            raise ValueError("Template name already exists") from exc
        if template is None:
            raise ValueError("Template not found")

        if make_default:
            await self._repository.set_default(template_id)
            template = await self._repository.get_by_id(template_id) or template
        return template

    async def delete_template(self, template_id: int) -> None:
        template = await self._repository.get_by_id(template_id)
        if template is None:
            raise ValueError("Template not found")
        if template.is_default:
            raise ValueError("Default template cannot be deleted")
        deleted = await self._repository.delete(template_id)
        if not deleted:
            raise ValueError("Template not found")
