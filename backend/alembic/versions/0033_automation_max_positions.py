"""Add max_positions to automation config.

Revision ID: 0033_automation_max_positions
Revises: 0032_pending_entry_lifecycle
Create Date: 2026-04-02 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0033_automation_max_positions"
down_revision = "0032_pending_entry_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "automation_config",
        sa.Column(
            "max_positions",
            sa.Integer(),
            nullable=False,
            server_default="3",
        ),
    )


def downgrade() -> None:
    op.drop_column("automation_config", "max_positions")
