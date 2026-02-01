from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AccountSetupModel(Base):
    __tablename__ = "account_setup"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    portfolio_exposure_pct: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        CheckConstraint("portfolio_exposure_pct >= 0", name="ck_account_setup_exposure_min"),
        CheckConstraint("portfolio_exposure_pct <= 100", name="ck_account_setup_exposure_max"),
    )
