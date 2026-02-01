"""Create dynamic asset config table.

Revision ID: 0013_dynamic_assets_config
Revises: 0012_create_agent_provider_configs
Create Date: 2024-09-10 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0013_dynamic_assets_config"
down_revision = "0012_create_agent_provider_configs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dynamic_asset_config",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("sources", sa.JSON(), nullable=True),
        sa.Column(
            "refresh_interval_seconds",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("600"),
        ),
        sa.Column("last_fetch_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_assets", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("dynamic_asset_config")
