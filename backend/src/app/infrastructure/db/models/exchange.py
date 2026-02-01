from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ExchangeAccountModel(Base):
    __tablename__ = "exchange_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    exchange: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    is_testnet: Mapped[bool] = mapped_column(Boolean, default=False)
    wallet_address: Mapped[str | None] = mapped_column(String(120), nullable=True)
    validation_status: Mapped[str] = mapped_column(String(20), nullable=False, default="unvalidated")
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    validation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    credentials: Mapped["ExchangeCredentialModel"] = relationship(
        "ExchangeCredentialModel",
        back_populates="account",
        uselist=False,
        cascade="all, delete-orphan",
    )


class ExchangeCredentialModel(Base):
    __tablename__ = "exchange_credentials"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("exchange_accounts.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    api_secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    passphrase_encrypted: Mapped[str] = mapped_column(Text, nullable=True)
    agent_key_encrypted: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    account: Mapped[ExchangeAccountModel] = relationship("ExchangeAccountModel", back_populates="credentials")
