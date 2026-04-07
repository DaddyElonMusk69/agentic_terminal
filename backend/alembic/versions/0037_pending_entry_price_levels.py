"""Persist explicit pending-entry protection price levels.

Revision ID: 0037_pending_entry_price_levels
Revises: 0036_active_position_origin_protection_intent
Create Date: 2026-04-05 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0037_pending_entry_price_levels"
down_revision = "0036_active_position_origin_protection_intent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pending_entry_order", sa.Column("stop_loss", sa.Float(), nullable=True))
    op.add_column("pending_entry_order", sa.Column("take_profit", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("pending_entry_order", "take_profit")
    op.drop_column("pending_entry_order", "stop_loss")
