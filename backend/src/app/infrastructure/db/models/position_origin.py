from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ActivePositionOriginModel(Base):
    __tablename__ = "active_position_origin"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("exchange_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    anchor_frame: Mapped[str | None] = mapped_column(Text, nullable=True)
    active_tunnel: Mapped[list | None] = mapped_column(JSON, nullable=True)
    stop_loss_roe: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit_roe: Mapped[float | None] = mapped_column(Float, nullable=True)
    position_side: Mapped[str | None] = mapped_column(String(10), nullable=True)
    exchange_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    peak_roe: Mapped[float | None] = mapped_column(Float, nullable=True)
    peak_roe_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    peak_roe_basis_entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    peak_roe_basis_size: Mapped[float | None] = mapped_column(Float, nullable=True)
    peak_roe_basis_leverage: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint("account_id", "symbol", name="uq_active_position_origin_account_symbol"),
    )
