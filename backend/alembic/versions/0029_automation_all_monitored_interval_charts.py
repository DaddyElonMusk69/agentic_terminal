"""Add use_all_monitored_interval_charts to automation_config.

Revision ID: 0029_automation_all_monitored_interval_charts
Revises: 0028_automation_reverse_order_enabled
Create Date: 2026-03-14 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0029_automation_all_monitored_interval_charts"
down_revision = "0028_automation_reverse_order_enabled"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "automation_config",
        sa.Column(
            "use_all_monitored_interval_charts",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("automation_config", "use_all_monitored_interval_charts")
