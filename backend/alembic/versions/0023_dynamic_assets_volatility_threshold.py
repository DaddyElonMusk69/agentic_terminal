"""Add volatility_threshold_pct to dynamic_asset_config.

Revision ID: 0023_dynamic_assets_volatility_threshold
Revises: 0022_ema_state_manager_event_flags
Create Date: 2026-02-07 15:36:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0023_dynamic_assets_volatility_threshold"
down_revision = "0022_ema_state_manager_event_flags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dynamic_asset_config",
        sa.Column(
            "volatility_threshold_pct",
            sa.Float(),
            nullable=False,
            server_default=sa.text("20.0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("dynamic_asset_config", "volatility_threshold_pct")
