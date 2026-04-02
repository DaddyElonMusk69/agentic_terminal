from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, JSON, String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AutomationConfigModel(Base):
    __tablename__ = "automation_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execution_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="dry_run")
    ema_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    quant_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    pending_entry_timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=900)
    max_positions: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reasoning_effort: Mapped[str | None] = mapped_column(String(20), nullable=True)
    include_entry_timing_15m_chart: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    use_all_monitored_interval_charts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reverse_order_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    vegas_prompt_configs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class AutomationSessionModel(Base):
    __tablename__ = "automation_session"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="dry_run")
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    total_cycles: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    prompt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    config_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class AutomationLogModel(Base):
    __tablename__ = "automation_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("automation_session.id"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    log_type: Mapped[str] = mapped_column(String(20), nullable=False, default="system")
    cycle_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class AutomationTradeModel(Base):
    __tablename__ = "automation_trade"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("automation_session.id"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    cycle_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[str | None] = mapped_column(String(10), nullable=True)
    action: Mapped[str | None] = mapped_column(String(20), nullable=True)
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    size_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signal_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    llm_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_response_full: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    fill_price: Mapped[float | None] = mapped_column(Float, nullable=True)
