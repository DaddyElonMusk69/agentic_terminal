"""Create risk management config.

Revision ID: 0019_risk_management_config
Revises: 0018_trade_guard_config_update
Create Date: 2026-01-30 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0019_risk_management_config"
down_revision = "0018_trade_guard_config_update"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "risk_management_config",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("final_goal_usd", sa.Float(), nullable=False),
        sa.Column("exposure_pct", sa.Float(), nullable=False),
        sa.Column("goal_deadline", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("final_goal_usd >= 0", name="ck_risk_goal_min"),
        sa.CheckConstraint("exposure_pct >= 1", name="ck_risk_exposure_min"),
        sa.CheckConstraint("exposure_pct <= 100", name="ck_risk_exposure_max"),
    )

    conn = op.get_bind()
    existing = conn.execute(sa.text("SELECT COUNT(*) FROM risk_management_config"))
    if existing.scalar() == 0:
        conn.execute(
            sa.text(
                "INSERT INTO risk_management_config "
                "(final_goal_usd, exposure_pct, goal_deadline, created_at, updated_at) "
                "VALUES (:final_goal_usd, :exposure_pct, :goal_deadline, :created_at, :updated_at)"
            ),
            {
                "final_goal_usd": 0,
                "exposure_pct": 20,
                "goal_deadline": None,
                "created_at": "2026-01-30T00:00:00Z",
                "updated_at": "2026-01-30T00:00:00Z",
            },
        )


def downgrade() -> None:
    op.drop_table("risk_management_config")
