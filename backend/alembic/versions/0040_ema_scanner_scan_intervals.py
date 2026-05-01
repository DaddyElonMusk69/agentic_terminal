"""Add EMA scanner interval selection and lower BB HTF floor.

Revision ID: 0040_ema_scanner_scan_intervals
Revises: 0039_active_position_origin_peak_roe_state
Create Date: 2026-04-26 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0040_ema_scanner_scan_intervals"
down_revision = "0039_active_position_origin_peak_roe_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ema_scanner_config",
        sa.Column("scan_intervals", sa.JSON(), nullable=True),
    )
    with op.batch_alter_table("ema_state_manager_config") as batch_op:
        batch_op.drop_constraint("ck_ema_state_bb_htf_min", type_="check")
        batch_op.create_check_constraint(
            "ck_ema_state_bb_htf_min",
            "bb_htf_min_interval_minutes >= 15",
        )


def downgrade() -> None:
    with op.batch_alter_table("ema_state_manager_config") as batch_op:
        batch_op.drop_constraint("ck_ema_state_bb_htf_min", type_="check")
        batch_op.create_check_constraint(
            "ck_ema_state_bb_htf_min",
            "bb_htf_min_interval_minutes >= 60",
        )
    op.drop_column("ema_scanner_config", "scan_intervals")
