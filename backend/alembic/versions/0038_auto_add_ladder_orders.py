"""Add persistent ladder-order fields to auto-add tranches.

Revision ID: 0038_auto_add_ladder_orders
Revises: 0037_pending_entry_price_levels
Create Date: 2026-04-05 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0038_auto_add_ladder_orders"
down_revision = "0037_pending_entry_price_levels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "auto_add_tranche",
        sa.Column("status", sa.String(length=16), nullable=False, server_default="PLACED"),
    )
    op.add_column(
        "auto_add_tranche",
        sa.Column("exchange_order_id", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "auto_add_tranche",
        sa.Column("trigger_price", sa.Float(), nullable=True),
    )
    op.add_column(
        "auto_add_tranche",
        sa.Column("last_error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("auto_add_tranche", "last_error")
    op.drop_column("auto_add_tranche", "trigger_price")
    op.drop_column("auto_add_tranche", "exchange_order_id")
    op.drop_column("auto_add_tranche", "status")
