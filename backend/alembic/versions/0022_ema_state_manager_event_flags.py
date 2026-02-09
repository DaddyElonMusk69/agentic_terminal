"""Add EMA state manager event toggle flags.

Revision ID: 0022_ema_state_manager_event_flags
Revises: 0021_automation_history
Create Date: 2026-02-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0022_ema_state_manager_event_flags"
down_revision = "0021_automation_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ema_state_manager_config",
        sa.Column(
            "emit_new_resonance",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "ema_state_manager_config",
        sa.Column(
            "emit_resonance_increase",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "ema_state_manager_config",
        sa.Column(
            "emit_structure_shift",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "ema_state_manager_config",
        sa.Column(
            "emit_resonance_refresh",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "ema_state_manager_config",
        sa.Column(
            "emit_bb_rejection_upper",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "ema_state_manager_config",
        sa.Column(
            "emit_bb_rejection_lower",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "ema_state_manager_config",
        sa.Column(
            "emit_position_management",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "ema_state_manager_config",
        sa.Column(
            "emit_bb_exit_warning",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    op.alter_column("ema_state_manager_config", "emit_new_resonance", server_default=None)
    op.alter_column("ema_state_manager_config", "emit_resonance_increase", server_default=None)
    op.alter_column("ema_state_manager_config", "emit_structure_shift", server_default=None)
    op.alter_column("ema_state_manager_config", "emit_resonance_refresh", server_default=None)
    op.alter_column("ema_state_manager_config", "emit_bb_rejection_upper", server_default=None)
    op.alter_column("ema_state_manager_config", "emit_bb_rejection_lower", server_default=None)
    op.alter_column("ema_state_manager_config", "emit_position_management", server_default=None)
    op.alter_column("ema_state_manager_config", "emit_bb_exit_warning", server_default=None)


def downgrade() -> None:
    op.drop_column("ema_state_manager_config", "emit_bb_exit_warning")
    op.drop_column("ema_state_manager_config", "emit_position_management")
    op.drop_column("ema_state_manager_config", "emit_bb_rejection_lower")
    op.drop_column("ema_state_manager_config", "emit_bb_rejection_upper")
    op.drop_column("ema_state_manager_config", "emit_resonance_refresh")
    op.drop_column("ema_state_manager_config", "emit_structure_shift")
    op.drop_column("ema_state_manager_config", "emit_resonance_increase")
    op.drop_column("ema_state_manager_config", "emit_new_resonance")
