"""Create active_position_origin table.

Revision ID: 0030_active_position_origin
Revises: 0029_automation_all_monitored_interval_charts
Create Date: 2026-03-18 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0030_active_position_origin"
down_revision = "0029_automation_all_monitored_interval_charts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "active_position_origin",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("anchor_frame", sa.Text(), nullable=True),
        sa.Column("active_tunnel", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["exchange_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id",
            "symbol",
            name="uq_active_position_origin_account_symbol",
        ),
    )


def downgrade() -> None:
    op.drop_table("active_position_origin")
