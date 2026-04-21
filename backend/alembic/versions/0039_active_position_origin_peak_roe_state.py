"""Persist live position runtime state on active_position_origin.

Revision ID: 0039_active_position_origin_peak_roe_state
Revises: 0039_automation_entry_timing_5m_chart
Create Date: 2026-04-21 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0039_active_position_origin_peak_roe_state"
down_revision = "0039_automation_entry_timing_5m_chart"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "active_position_origin",
        sa.Column("position_side", sa.String(length=10), nullable=True),
    )
    op.add_column(
        "active_position_origin",
        sa.Column("exchange_opened_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "active_position_origin",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "active_position_origin",
        sa.Column("peak_roe", sa.Float(), nullable=True),
    )
    op.add_column(
        "active_position_origin",
        sa.Column("peak_roe_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "active_position_origin",
        sa.Column("peak_roe_basis_entry_price", sa.Float(), nullable=True),
    )
    op.add_column(
        "active_position_origin",
        sa.Column("peak_roe_basis_size", sa.Float(), nullable=True),
    )
    op.add_column(
        "active_position_origin",
        sa.Column("peak_roe_basis_leverage", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("active_position_origin", "peak_roe_basis_leverage")
    op.drop_column("active_position_origin", "peak_roe_basis_size")
    op.drop_column("active_position_origin", "peak_roe_basis_entry_price")
    op.drop_column("active_position_origin", "peak_roe_updated_at")
    op.drop_column("active_position_origin", "peak_roe")
    op.drop_column("active_position_origin", "last_seen_at")
    op.drop_column("active_position_origin", "exchange_opened_at")
    op.drop_column("active_position_origin", "position_side")
