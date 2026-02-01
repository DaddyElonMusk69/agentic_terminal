from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, JSON, Text, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TelegramConfigModel(Base):
    __tablename__ = "telegram_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bot_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    chat_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    recipients: Mapped[list | None] = mapped_column(JSON, nullable=True)
    notifications: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    parse_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="Markdown")
    disable_notification: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
