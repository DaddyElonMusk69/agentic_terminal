"""Add include_entry_timing_15m_chart to automation_config.

Revision ID: 0027_automation_entry_timing_15m_chart
Revises: 0026_dynamic_assets_oi_source
Create Date: 2026-03-06 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0027_automation_entry_timing_15m_chart"
down_revision = "0026_dynamic_assets_oi_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "automation_config",
        sa.Column(
            "include_entry_timing_15m_chart",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("automation_config", "include_entry_timing_15m_chart")
