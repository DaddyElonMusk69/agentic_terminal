from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PendingEntryOrderModel(Base):
    __tablename__ = "pending_entry_order"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "exchange_order_id",
            name="uq_pending_entry_account_order",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(36), nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    exchange_symbol: Mapped[str] = mapped_column(String(40), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    exchange_order_id: Mapped[str] = mapped_column(String(100), nullable=False)
    limit_price: Mapped[float] = mapped_column(Float, nullable=False)
    intended_size_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    intended_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    filled_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    leverage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    time_in_force: Mapped[str | None] = mapped_column(String(10), nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss_roe: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit_roe: Mapped[float | None] = mapped_column(Float, nullable=True)
    anchor_frame: Mapped[str | None] = mapped_column(String(20), nullable=True)
    active_tunnel: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RESTING")
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
