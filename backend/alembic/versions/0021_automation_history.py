"""Create automation session history tables.

Revision ID: 0021_automation_history
Revises: 0020_trade_guard_default_leverage
Create Date: 2026-02-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "0021_automation_history"
down_revision = "0020_trade_guard_default_leverage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "automation_session",
        sa.Column("id", sa.String(length=50), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "execution_mode",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'dry_run'"),
        ),
        sa.Column("provider", sa.String(length=80), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column(
            "total_cycles",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "total_trades",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "total_pnl",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "prompt_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("config_snapshot", sa.JSON(), nullable=True),
    )

    op.create_table(
        "automation_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.String(length=50),
            sa.ForeignKey("automation_session.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("log_type", sa.String(length=20), nullable=False),
        sa.Column(
            "cycle_number",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("data", sa.JSON(), nullable=True),
    )

    op.create_index(
        "idx_automation_log_session",
        "automation_log",
        ["session_id"],
    )
    op.create_index(
        "idx_automation_log_type",
        "automation_log",
        ["log_type"],
    )
    op.create_index(
        "idx_automation_log_created",
        "automation_log",
        ["created_at"],
    )

    op.create_table(
        "automation_trade",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.String(length=50),
            sa.ForeignKey("automation_session.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "cycle_number",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=True),
        sa.Column("action", sa.String(length=20), nullable=True),
        sa.Column("entry_price", sa.Float(), nullable=True),
        sa.Column("exit_price", sa.Float(), nullable=True),
        sa.Column("size_usd", sa.Float(), nullable=True),
        sa.Column("pnl", sa.Float(), nullable=True),
        sa.Column("pnl_pct", sa.Float(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signal_data", sa.JSON(), nullable=True),
        sa.Column("llm_reasoning", sa.Text(), nullable=True),
        sa.Column("llm_response_full", sa.Text(), nullable=True),
        sa.Column("order_id", sa.String(length=100), nullable=True),
        sa.Column("fill_price", sa.Float(), nullable=True),
    )

    op.create_index(
        "idx_automation_trade_session",
        "automation_trade",
        ["session_id"],
    )
    op.create_index(
        "idx_automation_trade_symbol",
        "automation_trade",
        ["symbol"],
    )
    op.create_index(
        "idx_automation_trade_status",
        "automation_trade",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("idx_automation_trade_status", table_name="automation_trade")
    op.drop_index("idx_automation_trade_symbol", table_name="automation_trade")
    op.drop_index("idx_automation_trade_session", table_name="automation_trade")
    op.drop_table("automation_trade")

    op.drop_index("idx_automation_log_created", table_name="automation_log")
    op.drop_index("idx_automation_log_type", table_name="automation_log")
    op.drop_index("idx_automation_log_session", table_name="automation_log")
    op.drop_table("automation_log")

    op.drop_table("automation_session")
