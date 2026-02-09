"""Add new_resonance_min_touches column.

Revision ID: 0024_new_resonance_min_touches
Revises: 0023_dynamic_assets_volatility_threshold
Create Date: 2026-02-09 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0024_new_resonance_min_touches"
down_revision = "0023_dynamic_assets_volatility_threshold"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ema_state_manager_config",
        sa.Column(
            "new_resonance_min_touches",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.alter_column(
        "ema_state_manager_config",
        "new_resonance_min_touches",
        server_default=None,
    )
    op.create_check_constraint(
        "ck_ema_state_new_res_touches_min",
        "ema_state_manager_config",
        "new_resonance_min_touches >= 1",
    )
    op.create_check_constraint(
        "ck_ema_state_new_res_touches_max",
        "ema_state_manager_config",
        "new_resonance_min_touches <= 30",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_ema_state_new_res_touches_max",
        "ema_state_manager_config",
        type_="check",
    )
    op.drop_constraint(
        "ck_ema_state_new_res_touches_min",
        "ema_state_manager_config",
        type_="check",
    )
    op.drop_column("ema_state_manager_config", "new_resonance_min_touches")
