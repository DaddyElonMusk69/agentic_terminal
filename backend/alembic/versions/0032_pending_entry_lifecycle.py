"""Add pending entry lifecycle storage.

Revision ID: 0032_pending_entry_lifecycle
Revises: 0031_automation_reasoning_effort
Create Date: 2026-03-30 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0032_pending_entry_lifecycle"
down_revision = "0031_automation_reasoning_effort"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "automation_config",
        sa.Column(
            "pending_entry_timeout_seconds",
            sa.Integer(),
            nullable=False,
            server_default="900",
        ),
    )

    op.create_table(
        "pending_entry_order",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=50), nullable=True),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("exchange_symbol", sa.String(length=40), nullable=False),
        sa.Column("side", sa.String(length=10), nullable=False),
        sa.Column("exchange_order_id", sa.String(length=100), nullable=False),
        sa.Column("limit_price", sa.Float(), nullable=False),
        sa.Column("intended_size_usd", sa.Float(), nullable=True),
        sa.Column("intended_quantity", sa.Float(), nullable=True),
        sa.Column("filled_quantity", sa.Float(), nullable=True),
        sa.Column("leverage", sa.Integer(), nullable=True),
        sa.Column("time_in_force", sa.String(length=10), nullable=True),
        sa.Column("stop_loss_roe", sa.Float(), nullable=True),
        sa.Column("take_profit_roe", sa.Float(), nullable=True),
        sa.Column("anchor_frame", sa.String(length=20), nullable=True),
        sa.Column("active_tunnel", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("order_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id",
            "exchange_order_id",
            name="uq_pending_entry_account_order",
        ),
    )


def downgrade() -> None:
    op.drop_table("pending_entry_order")
    op.drop_column("automation_config", "pending_entry_timeout_seconds")
