from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, JSON, String, Text, CheckConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OiRankConfigModel(Base):
    __tablename__ = "oi_rank_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    refresh_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    stale_ttl_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        CheckConstraint("refresh_interval_minutes >= 10", name="ck_oi_rank_refresh_min"),
        CheckConstraint("refresh_interval_minutes <= 720", name="ck_oi_rank_refresh_max"),
        CheckConstraint("stale_ttl_minutes >= refresh_interval_minutes", name="ck_oi_rank_stale_ge_refresh"),
    )


class OiRankCacheModel(Base):
    __tablename__ = "oi_rank_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    interval: Mapped[str] = mapped_column(String(10), nullable=False)
    metric: Mapped[str] = mapped_column(String(10), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    limit: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    payload: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="warming")
    data_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refresh_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint("interval", "metric", "direction", name="uq_oi_rank_cache_key"),
    )

