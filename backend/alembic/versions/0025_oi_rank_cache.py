"""Add oi_rank_config and oi_rank_cache tables.

Revision ID: 0025_oi_rank_cache
Revises: 0024_new_resonance_min_touches
Create Date: 2026-02-19 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0025_oi_rank_cache"
down_revision = "0024_new_resonance_min_touches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oi_rank_config",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("refresh_interval_minutes", sa.Integer(), nullable=False, server_default=sa.text("30")),
        sa.Column("stale_ttl_minutes", sa.Integer(), nullable=False, server_default=sa.text("90")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("refresh_interval_minutes >= 10", name="ck_oi_rank_refresh_min"),
        sa.CheckConstraint("refresh_interval_minutes <= 720", name="ck_oi_rank_refresh_max"),
        sa.CheckConstraint("stale_ttl_minutes >= refresh_interval_minutes", name="ck_oi_rank_stale_ge_refresh"),
    )

    op.create_table(
        "oi_rank_cache",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("interval", sa.String(length=10), nullable=False),
        sa.Column("metric", sa.String(length=10), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("limit", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'warming'")),
        sa.Column("data_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refresh_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("interval", "metric", "direction", name="uq_oi_rank_cache_key"),
    )


def downgrade() -> None:
    op.drop_table("oi_rank_cache")
    op.drop_table("oi_rank_config")

