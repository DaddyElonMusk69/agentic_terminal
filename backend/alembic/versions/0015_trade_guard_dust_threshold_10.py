"""Update trade guard dust threshold to $10.

Revision ID: 0015_trade_guard_dust_threshold_10
Revises: 0014_telegram_config
Create Date: 2024-09-12 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0015_trade_guard_dust_threshold_10"
down_revision = "0014_telegram_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE trade_guard_config SET dust_threshold_usd = :threshold"
        ).bindparams(threshold=10.0)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE trade_guard_config SET dust_threshold_usd = :threshold"
        ).bindparams(threshold=15.0)
    )
