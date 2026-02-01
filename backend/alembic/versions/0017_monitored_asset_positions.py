"""Create monitored asset positions table.

Revision ID: 0017_monitored_asset_positions
Revises: 0016_automation_config
Create Date: 2024-09-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0017_monitored_asset_positions"
down_revision = "0016_automation_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monitored_asset_positions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(length=50), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("monitored_asset_positions")
