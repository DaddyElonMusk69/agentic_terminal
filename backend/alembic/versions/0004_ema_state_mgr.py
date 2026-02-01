"""Create EMA state manager config.

Revision ID: 0004_ema_state_mgr
Revises: 0003_create_ema_scanner_config
Create Date: 2024-09-02 00:00:03.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_ema_state_mgr"
down_revision = "0003_create_ema_scanner_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ema_state_manager_config",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("min_resonance", sa.Integer(), nullable=False),
        sa.Column("ema_resonance_cooldown_seconds", sa.Integer(), nullable=False),
        sa.Column("bb_rejection_cooldown_seconds", sa.Integer(), nullable=False),
        sa.Column("bb_exit_warning_cooldown_seconds", sa.Integer(), nullable=False),
        sa.Column("position_check_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("bb_rejection_min_touches", sa.Integer(), nullable=False),
        sa.Column("bb_htf_min_interval_minutes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("min_resonance >= 1", name="ck_ema_state_min_resonance_min"),
        sa.CheckConstraint("min_resonance <= 5", name="ck_ema_state_min_resonance_max"),
        sa.CheckConstraint(
            "ema_resonance_cooldown_seconds >= 60",
            name="ck_ema_state_ema_resonance_cd_min",
        ),
        sa.CheckConstraint(
            "ema_resonance_cooldown_seconds <= 3600",
            name="ck_ema_state_ema_resonance_cd_max",
        ),
        sa.CheckConstraint(
            "bb_rejection_cooldown_seconds >= 60",
            name="ck_ema_state_bb_rejection_cd_min",
        ),
        sa.CheckConstraint(
            "bb_rejection_cooldown_seconds <= 3600",
            name="ck_ema_state_bb_rejection_cd_max",
        ),
        sa.CheckConstraint(
            "bb_exit_warning_cooldown_seconds >= 60",
            name="ck_ema_state_bb_exit_cd_min",
        ),
        sa.CheckConstraint(
            "bb_exit_warning_cooldown_seconds <= 3600",
            name="ck_ema_state_bb_exit_cd_max",
        ),
        sa.CheckConstraint(
            "position_check_interval_seconds >= 60",
            name="ck_ema_state_position_check_min",
        ),
        sa.CheckConstraint(
            "position_check_interval_seconds <= 3600",
            name="ck_ema_state_position_check_max",
        ),
        sa.CheckConstraint(
            "bb_rejection_min_touches >= 1",
            name="ck_ema_state_bb_rejection_touches_min",
        ),
        sa.CheckConstraint(
            "bb_rejection_min_touches <= 30",
            name="ck_ema_state_bb_rejection_touches_max",
        ),
        sa.CheckConstraint(
            "bb_htf_min_interval_minutes >= 60",
            name="ck_ema_state_bb_htf_min",
        ),
    )

    conn = op.get_bind()
    existing_config = conn.execute(sa.text("SELECT COUNT(*) FROM ema_state_manager_config"))
    if existing_config.scalar() == 0:
        conn.execute(
            sa.text(
                "INSERT INTO ema_state_manager_config "
                "(min_resonance, ema_resonance_cooldown_seconds, bb_rejection_cooldown_seconds, "
                "bb_exit_warning_cooldown_seconds, position_check_interval_seconds, "
                "bb_rejection_min_touches, bb_htf_min_interval_minutes, created_at, updated_at) "
                "VALUES (:min_resonance, :ema_resonance_cooldown_seconds, :bb_rejection_cooldown_seconds, "
                ":bb_exit_warning_cooldown_seconds, :position_check_interval_seconds, "
                ":bb_rejection_min_touches, :bb_htf_min_interval_minutes, :created_at, :updated_at)"
            ),
            {
                "min_resonance": 2,
                "ema_resonance_cooldown_seconds": 600,
                "bb_rejection_cooldown_seconds": 1200,
                "bb_exit_warning_cooldown_seconds": 600,
                "position_check_interval_seconds": 1800,
                "bb_rejection_min_touches": 10,
                "bb_htf_min_interval_minutes": 480,
                "created_at": "2024-09-02T00:00:00Z",
                "updated_at": "2024-09-02T00:00:00Z",
            },
        )


def downgrade() -> None:
    op.drop_table("ema_state_manager_config")
