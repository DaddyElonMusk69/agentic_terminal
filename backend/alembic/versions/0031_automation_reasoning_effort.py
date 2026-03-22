"""Add reasoning_effort to automation_config.

Revision ID: 0031_automation_reasoning_effort
Revises: 0030_active_position_origin
Create Date: 2026-03-20 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0031_automation_reasoning_effort"
down_revision = "0030_active_position_origin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "automation_config",
        sa.Column("reasoning_effort", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("automation_config", "reasoning_effort")
