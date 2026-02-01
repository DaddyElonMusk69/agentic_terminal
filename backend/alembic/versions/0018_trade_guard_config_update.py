"""Add trade guard TP ROE limits and position tier ranges.

Revision ID: 0018_trade_guard_config_update
Revises: 0017_monitored_asset_positions
Create Date: 2026-01-29 00:00:00.000000
"""
import json

from alembic import op
import sqlalchemy as sa


revision = "0018_trade_guard_config_update"
down_revision = "0017_monitored_asset_positions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "trade_guard_config",
        sa.Column(
            "tp_min_roe",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.05"),
        ),
    )
    op.add_column(
        "trade_guard_config",
        sa.Column(
            "tp_max_roe",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.2"),
        ),
    )
    op.add_column(
        "trade_guard_config",
        sa.Column(
            "position_tier_ranges",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )

    tier_ranges = json.dumps(
        [
            {"tier": 1, "min_pct": 0.70, "max_pct": 1.00},
            {"tier": 2, "min_pct": 0.35, "max_pct": 0.70},
            {"tier": 3, "min_pct": 0.15, "max_pct": 0.35},
        ]
    )
    op.execute(
        sa.text(
            "UPDATE trade_guard_config "
            "SET tp_min_roe = :tp_min, tp_max_roe = :tp_max, position_tier_ranges = :ranges"
        ).bindparams(tp_min=0.05, tp_max=0.2, ranges=tier_ranges)
    )

    op.create_check_constraint(
        "ck_trade_guard_tp_min_roe",
        "trade_guard_config",
        "tp_min_roe > 0",
    )
    op.create_check_constraint(
        "ck_trade_guard_tp_max_roe",
        "trade_guard_config",
        "tp_max_roe >= tp_min_roe",
    )

    op.alter_column("trade_guard_config", "tp_min_roe", server_default=None)
    op.alter_column("trade_guard_config", "tp_max_roe", server_default=None)
    op.alter_column("trade_guard_config", "position_tier_ranges", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_trade_guard_tp_max_roe", "trade_guard_config", type_="check")
    op.drop_constraint("ck_trade_guard_tp_min_roe", "trade_guard_config", type_="check")
    op.drop_column("trade_guard_config", "position_tier_ranges")
    op.drop_column("trade_guard_config", "tp_max_roe")
    op.drop_column("trade_guard_config", "tp_min_roe")
