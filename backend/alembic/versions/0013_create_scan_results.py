"""Create scan_result table.

Revision ID: 0013_create_scan_results
Revises: 0012_create_agent_provider_configs
Create Date: 2024-09-12 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "0013_create_scan_results"
down_revision = "0013_dynamic_assets_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if "scan_result" in inspector.get_table_names():
        return

    op.create_table(
        "scan_result",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("data", sa.JSON(), nullable=True),
    )
    op.create_index("ix_scan_result_date", "scan_result", ["date"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if "scan_result" not in inspector.get_table_names():
        return
    op.drop_index("ix_scan_result_date", table_name="scan_result")
    op.drop_table("scan_result")
