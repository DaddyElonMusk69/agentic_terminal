from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, Integer, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RiskManagementConfigModel(Base):
    __tablename__ = "risk_management_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    final_goal_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    exposure_pct: Mapped[float] = mapped_column(Float, nullable=False, default=20.0)
    goal_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        CheckConstraint("final_goal_usd >= 0", name="ck_risk_goal_min"),
        CheckConstraint("exposure_pct >= 1", name="ck_risk_exposure_min"),
        CheckConstraint("exposure_pct <= 100", name="ck_risk_exposure_max"),
    )
