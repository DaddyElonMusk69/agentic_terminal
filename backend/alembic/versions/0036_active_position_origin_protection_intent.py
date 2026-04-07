"""Persist protection intent on active_position_origin.

Revision ID: 0036_active_position_origin_protection_intent
Revises: 0035_auto_add_capacity_retry
Create Date: 2026-04-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0036_active_position_origin_protection_intent"
down_revision = "0035_auto_add_capacity_retry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "active_position_origin",
        sa.Column("stop_loss_roe", sa.Float(), nullable=True),
    )
    op.add_column(
        "active_position_origin",
        sa.Column("take_profit_roe", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("active_position_origin", "take_profit_roe")
    op.drop_column("active_position_origin", "stop_loss_roe")
