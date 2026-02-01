from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EmaStateManagerConfigModel(Base):
    __tablename__ = "ema_state_manager_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    min_resonance: Mapped[int] = mapped_column(Integer, nullable=False)
    ema_resonance_cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    bb_rejection_cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    bb_exit_warning_cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    position_check_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    bb_rejection_min_touches: Mapped[int] = mapped_column(Integer, nullable=False)
    bb_htf_min_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        CheckConstraint("min_resonance >= 1", name="ck_ema_state_min_resonance_min"),
        CheckConstraint("min_resonance <= 5", name="ck_ema_state_min_resonance_max"),
        CheckConstraint(
            "ema_resonance_cooldown_seconds >= 60",
            name="ck_ema_state_ema_resonance_cd_min",
        ),
        CheckConstraint(
            "ema_resonance_cooldown_seconds <= 3600",
            name="ck_ema_state_ema_resonance_cd_max",
        ),
        CheckConstraint(
            "bb_rejection_cooldown_seconds >= 60",
            name="ck_ema_state_bb_rejection_cd_min",
        ),
        CheckConstraint(
            "bb_rejection_cooldown_seconds <= 3600",
            name="ck_ema_state_bb_rejection_cd_max",
        ),
        CheckConstraint(
            "bb_exit_warning_cooldown_seconds >= 60",
            name="ck_ema_state_bb_exit_cd_min",
        ),
        CheckConstraint(
            "bb_exit_warning_cooldown_seconds <= 3600",
            name="ck_ema_state_bb_exit_cd_max",
        ),
        CheckConstraint(
            "position_check_interval_seconds >= 60",
            name="ck_ema_state_position_check_min",
        ),
        CheckConstraint(
            "position_check_interval_seconds <= 3600",
            name="ck_ema_state_position_check_max",
        ),
        CheckConstraint(
            "bb_rejection_min_touches >= 1",
            name="ck_ema_state_bb_rejection_touches_min",
        ),
        CheckConstraint(
            "bb_rejection_min_touches <= 30",
            name="ck_ema_state_bb_rejection_touches_max",
        ),
        CheckConstraint(
            "bb_htf_min_interval_minutes >= 60",
            name="ck_ema_state_bb_htf_min",
        ),
    )
