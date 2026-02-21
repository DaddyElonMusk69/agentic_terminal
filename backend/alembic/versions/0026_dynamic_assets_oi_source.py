"""Add oi_source to dynamic_asset_config.

Revision ID: 0026_dynamic_assets_oi_source
Revises: 0025_oi_rank_cache
Create Date: 2026-02-19 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0026_dynamic_assets_oi_source"
down_revision = "0025_oi_rank_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dynamic_asset_config",
        sa.Column("oi_source", sa.Text(), nullable=False, server_default=sa.text("'nofx'")),
    )


def downgrade() -> None:
    op.drop_column("dynamic_asset_config", "oi_source")
