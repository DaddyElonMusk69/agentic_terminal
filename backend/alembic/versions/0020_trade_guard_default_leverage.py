"""Add default leverage to trade guard config.

Revision ID: 0020_trade_guard_default_leverage
Revises: 0019_risk_management_config
Create Date: 2026-01-31 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0020_trade_guard_default_leverage"
down_revision = "0019_risk_management_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "trade_guard_config",
        sa.Column(
            "default_leverage",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )

    op.create_check_constraint(
        "ck_trade_guard_default_leverage_min",
        "trade_guard_config",
        "default_leverage >= 1",
    )
    op.create_check_constraint(
        "ck_trade_guard_default_leverage_max",
        "trade_guard_config",
        "default_leverage <= 5",
    )

    op.alter_column("trade_guard_config", "default_leverage", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        "ck_trade_guard_default_leverage_max",
        "trade_guard_config",
        type_="check",
    )
    op.drop_constraint(
        "ck_trade_guard_default_leverage_min",
        "trade_guard_config",
        type_="check",
    )
    op.drop_column("trade_guard_config", "default_leverage")
