from __future__ import annotations

from typing import List, Optional, Protocol

from app.domain.prompt_builder.models import PromptTemplate


class PromptTemplateRepository(Protocol):
    async def list_all(self) -> List[PromptTemplate]:
        ...

    async def get_by_id(self, template_id: int) -> Optional[PromptTemplate]:
        ...

    async def get_default(self) -> Optional[PromptTemplate]:
        ...

    async def create(
        self,
        name: str,
        intro: str,
        response_format: str,
        quant_fields: Optional[List[str]],
        chart_defaults: Optional[dict],
        is_default: bool,
    ) -> PromptTemplate:
        ...

    async def update(
        self,
        template_id: int,
        fields: dict,
    ) -> Optional[PromptTemplate]:
        ...

    async def delete(self, template_id: int) -> bool:
        ...

    async def set_default(self, template_id: int) -> bool:
        ...


class QuantSnapshotProvider(Protocol):
    def get_snapshot(self, symbol: str, timeframe: str):
        ...


class ImageUploader(Protocol):
    async def upload(self, image_bytes: bytes, name: str) -> Optional[str]:
        ...
