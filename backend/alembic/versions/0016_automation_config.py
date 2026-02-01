"""Create automation config table.

Revision ID: 0016_automation_config
Revises: 0015_trade_guard_dust_threshold_10
Create Date: 2024-09-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0016_automation_config"
down_revision = "0015_trade_guard_dust_threshold_10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "automation_config",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "execution_mode",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'dry_run'"),
        ),
        sa.Column(
            "ema_interval_seconds",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("60"),
        ),
        sa.Column(
            "quant_interval_seconds",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("60"),
        ),
        sa.Column("provider", sa.String(length=80), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("vegas_prompt_configs", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("automation_config")
