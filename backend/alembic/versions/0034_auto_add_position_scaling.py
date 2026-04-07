"""Add auto-add automation config and persistence tables.

Revision ID: 0034_auto_add_position_scaling
Revises: 0033_automation_max_positions
Create Date: 2026-04-02 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0034_auto_add_position_scaling"
down_revision = "0033_automation_max_positions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "automation_config",
        sa.Column(
            "auto_add_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "automation_config",
        sa.Column(
            "auto_add_trigger_atr_multiple",
            sa.Float(),
            nullable=False,
            server_default="1.0",
        ),
    )
    op.add_column(
        "automation_config",
        sa.Column(
            "auto_add_tranche_margin_pct",
            sa.Float(),
            nullable=False,
            server_default="0.8",
        ),
    )
    op.add_column(
        "automation_config",
        sa.Column(
            "auto_add_max_tranches",
            sa.Integer(),
            nullable=False,
            server_default="3",
        ),
    )
    op.add_column(
        "automation_config",
        sa.Column(
            "auto_add_protected_stop_roe",
            sa.Float(),
            nullable=False,
            server_default="0.002",
        ),
    )

    op.create_table(
        "auto_add_position",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=50), nullable=True),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("side", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("initial_margin_used", sa.Float(), nullable=True),
        sa.Column("initial_stop_price", sa.Float(), nullable=True),
        sa.Column("original_risk_usd", sa.Float(), nullable=True),
        sa.Column("trigger_basis_price", sa.Float(), nullable=True),
        sa.Column("next_trigger_price", sa.Float(), nullable=True),
        sa.Column("initial_entry_price", sa.Float(), nullable=True),
        sa.Column("initial_quantity", sa.Float(), nullable=True),
        sa.Column("expected_quantity", sa.Float(), nullable=True),
        sa.Column("leverage", sa.Float(), nullable=True),
        sa.Column("add_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_tranches", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("trigger_atr_multiple", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("tranche_margin_pct", sa.Float(), nullable=False, server_default="0.8"),
        sa.Column("protected_stop_roe", sa.Float(), nullable=False, server_default="0.002"),
        sa.Column("last_atr_value", sa.Float(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_trade_guard_reason", sa.Text(), nullable=True),
        sa.Column("last_seen_position_size", sa.Float(), nullable=True),
        sa.Column("last_seen_entry_price", sa.Float(), nullable=True),
        sa.Column("last_seen_mark_price", sa.Float(), nullable=True),
        sa.Column("last_seen_margin", sa.Float(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auto_add_position_account_symbol", "auto_add_position", ["account_id", "symbol"])
    op.create_index("ix_auto_add_position_active", "auto_add_position", ["account_id", "active", "status"])

    op.create_table(
        "auto_add_tranche",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("auto_add_position_id", sa.String(length=36), nullable=False),
        sa.Column("tranche_index", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("fill_price", sa.Float(), nullable=True),
        sa.Column("filled_quantity", sa.Float(), nullable=True),
        sa.Column("margin_used", sa.Float(), nullable=True),
        sa.Column("position_notional_usd", sa.Float(), nullable=True),
        sa.Column("fill_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atr_value", sa.Float(), nullable=True),
        sa.Column("trigger_basis_price", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["auto_add_position_id"], ["auto_add_position.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("auto_add_position_id", "tranche_index", name="uq_auto_add_tranche_index"),
    )
    op.create_index("ix_auto_add_tranche_position", "auto_add_tranche", ["auto_add_position_id"])


def downgrade() -> None:
    op.drop_index("ix_auto_add_tranche_position", table_name="auto_add_tranche")
    op.drop_table("auto_add_tranche")
    op.drop_index("ix_auto_add_position_active", table_name="auto_add_position")
    op.drop_index("ix_auto_add_position_account_symbol", table_name="auto_add_position")
    op.drop_table("auto_add_position")

    op.drop_column("automation_config", "auto_add_protected_stop_roe")
    op.drop_column("automation_config", "auto_add_max_tranches")
    op.drop_column("automation_config", "auto_add_tranche_margin_pct")
    op.drop_column("automation_config", "auto_add_trigger_atr_multiple")
    op.drop_column("automation_config", "auto_add_enabled")
