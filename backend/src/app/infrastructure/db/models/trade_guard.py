from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Float, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TradeGuardConfigModel(Base):
    __tablename__ = "trade_guard_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    min_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    min_position_size: Mapped[float] = mapped_column(Float, nullable=False)
    sl_min_roe: Mapped[float] = mapped_column(Float, nullable=False)
    sl_max_roe: Mapped[float] = mapped_column(Float, nullable=False)
    tp_min_roe: Mapped[float] = mapped_column(Float, nullable=False)
    tp_max_roe: Mapped[float] = mapped_column(Float, nullable=False)
    dust_threshold_usd: Mapped[float] = mapped_column(Float, nullable=False)
    default_leverage: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    leverage_tiers: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)
    position_tier_ranges: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        CheckConstraint("min_confidence >= 0", name="ck_trade_guard_confidence_min"),
        CheckConstraint("min_confidence <= 100", name="ck_trade_guard_confidence_max"),
        CheckConstraint("min_position_size >= 0", name="ck_trade_guard_min_position_size"),
        CheckConstraint("sl_min_roe > 0", name="ck_trade_guard_sl_min_roe"),
        CheckConstraint("sl_max_roe >= sl_min_roe", name="ck_trade_guard_sl_max_roe"),
        CheckConstraint("tp_min_roe > 0", name="ck_trade_guard_tp_min_roe"),
        CheckConstraint("tp_max_roe >= tp_min_roe", name="ck_trade_guard_tp_max_roe"),
        CheckConstraint("dust_threshold_usd >= 0", name="ck_trade_guard_dust_min"),
        CheckConstraint("default_leverage >= 1", name="ck_trade_guard_default_leverage_min"),
        CheckConstraint("default_leverage <= 5", name="ck_trade_guard_default_leverage_max"),
    )
