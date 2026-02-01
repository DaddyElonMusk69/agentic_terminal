from typing import List, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.prompt_builder.interfaces import PromptTemplateRepository
from app.domain.prompt_builder.models import PromptTemplate
from app.infrastructure.db.models.prompt_template import PromptTemplateModel


class SqlPromptTemplateRepository(PromptTemplateRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def list_all(self) -> List[PromptTemplate]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(PromptTemplateModel).order_by(PromptTemplateModel.id)
            )
            return [_to_template(model) for model in result.scalars().all()]

    async def get_by_id(self, template_id: int) -> Optional[PromptTemplate]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(PromptTemplateModel).where(PromptTemplateModel.id == template_id)
            )
            model = result.scalars().first()
            return _to_template(model) if model else None

    async def get_default(self) -> Optional[PromptTemplate]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(PromptTemplateModel)
                .where(PromptTemplateModel.is_default.is_(True))
                .order_by(PromptTemplateModel.id)
            )
            model = result.scalars().first()
            return _to_template(model) if model else None

    async def create(
        self,
        name: str,
        intro: str,
        response_format: str,
        quant_fields: Optional[List[str]],
        chart_defaults: Optional[dict],
        is_default: bool,
    ) -> PromptTemplate:
        async with self._sessionmaker() as session:
            model = PromptTemplateModel(
                name=name,
                intro=intro,
                response_format=response_format,
                quant_fields=quant_fields,
                chart_defaults=chart_defaults,
                is_default=is_default,
            )
            session.add(model)
            await session.commit()
            await session.refresh(model)
            return _to_template(model)

    async def update(self, template_id: int, fields: dict) -> Optional[PromptTemplate]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(PromptTemplateModel).where(PromptTemplateModel.id == template_id)
            )
            model = result.scalars().first()
            if model is None:
                return None
            for key, value in fields.items():
                if hasattr(model, key):
                    setattr(model, key, value)
            await session.commit()
            await session.refresh(model)
            return _to_template(model)

    async def delete(self, template_id: int) -> bool:
        async with self._sessionmaker() as session:
            result = await session.execute(
                delete(PromptTemplateModel).where(PromptTemplateModel.id == template_id)
            )
            await session.commit()
            return result.rowcount > 0

    async def set_default(self, template_id: int) -> bool:
        async with self._sessionmaker() as session:
            await session.execute(update(PromptTemplateModel).values(is_default=False))
            result = await session.execute(
                select(PromptTemplateModel).where(PromptTemplateModel.id == template_id)
            )
            model = result.scalars().first()
            if model is None:
                return False
            model.is_default = True
            await session.commit()
            return True


def _to_template(model: PromptTemplateModel) -> PromptTemplate:
    return PromptTemplate(
        id=model.id,
        name=model.name,
        intro=model.intro,
        response_format=model.response_format,
        quant_fields=model.quant_fields,
        chart_defaults=model.chart_defaults,
        is_default=bool(model.is_default),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )
