from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AutoAddPositionModel(Base):
    __tablename__ = "auto_add_position"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(36), nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    initial_margin_used: Mapped[float | None] = mapped_column(Float, nullable=True)
    initial_stop_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    original_risk_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    trigger_basis_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    next_trigger_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    initial_entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    initial_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    leverage: Mapped[float | None] = mapped_column(Float, nullable=True)
    add_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_tranches: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    trigger_atr_multiple: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    tranche_margin_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.80)
    protected_stop_roe: Mapped[float] = mapped_column(Float, nullable=False, default=0.002)
    last_atr_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_capacity_blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_trade_guard_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_seen_position_size: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_seen_entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_seen_mark_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_seen_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AutoAddTrancheModel(Base):
    __tablename__ = "auto_add_tranche"
    __table_args__ = (
        UniqueConstraint("auto_add_position_id", "tranche_index", name="uq_auto_add_tranche_index"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    auto_add_position_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("auto_add_position.id", ondelete="CASCADE"),
        nullable=False,
    )
    tranche_index: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PLACED")
    exchange_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    trigger_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    fill_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    filled_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    margin_used: Mapped[float | None] = mapped_column(Float, nullable=True)
    position_notional_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    fill_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    atr_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    trigger_basis_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
