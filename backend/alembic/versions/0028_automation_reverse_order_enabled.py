"""Add reverse_order_enabled to automation_config.

Revision ID: 0028_automation_reverse_order_enabled
Revises: 0027_automation_entry_timing_15m_chart
Create Date: 2026-03-08 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0028_automation_reverse_order_enabled"
down_revision = "0027_automation_entry_timing_15m_chart"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "automation_config",
        sa.Column(
            "reverse_order_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("automation_config", "reverse_order_enabled")
