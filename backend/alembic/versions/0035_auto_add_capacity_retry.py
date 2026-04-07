"""Add capacity-retry tracking to auto-add positions.

Revision ID: 0035_auto_add_capacity_retry
Revises: 0034_auto_add_position_scaling
Create Date: 2026-04-03 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0035_auto_add_capacity_retry"
down_revision = "0034_auto_add_position_scaling"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "auto_add_position",
        sa.Column("last_capacity_blocked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("auto_add_position", "last_capacity_blocked_at")
