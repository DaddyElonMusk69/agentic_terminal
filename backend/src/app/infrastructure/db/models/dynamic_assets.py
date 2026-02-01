from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DynamicAssetConfigModel(Base):
    __tablename__ = "dynamic_asset_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    sources: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    refresh_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=600)
    last_fetch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_assets: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
