"""Create trade guard config and account setup tables.

Revision ID: 0008_trade_guard
Revises: 0007_image_uploader_cfg
Create Date: 2024-09-02 00:00:10.000000
"""

import json

from alembic import op
import sqlalchemy as sa


revision = "0008_trade_guard"
down_revision = "0007_image_uploader_cfg"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_setup",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("portfolio_exposure_pct", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("portfolio_exposure_pct >= 0", name="ck_account_setup_exposure_min"),
        sa.CheckConstraint("portfolio_exposure_pct <= 100", name="ck_account_setup_exposure_max"),
    )

    op.create_table(
        "trade_guard_config",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("min_confidence", sa.Float(), nullable=False),
        sa.Column("min_position_size", sa.Float(), nullable=False),
        sa.Column("sl_min_roe", sa.Float(), nullable=False),
        sa.Column("sl_max_roe", sa.Float(), nullable=False),
        sa.Column("dust_threshold_usd", sa.Float(), nullable=False),
        sa.Column("leverage_tiers", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("min_confidence >= 0", name="ck_trade_guard_confidence_min"),
        sa.CheckConstraint("min_confidence <= 100", name="ck_trade_guard_confidence_max"),
        sa.CheckConstraint("min_position_size >= 0", name="ck_trade_guard_min_position_size"),
        sa.CheckConstraint("sl_min_roe > 0", name="ck_trade_guard_sl_min_roe"),
        sa.CheckConstraint("sl_max_roe >= sl_min_roe", name="ck_trade_guard_sl_max_roe"),
        sa.CheckConstraint("dust_threshold_usd >= 0", name="ck_trade_guard_dust_min"),
    )

    conn = op.get_bind()

    existing_setup = conn.execute(sa.text("SELECT COUNT(*) FROM account_setup"))
    if existing_setup.scalar() == 0:
        conn.execute(
            sa.text(
                "INSERT INTO account_setup "
                "(portfolio_exposure_pct, created_at, updated_at) "
                "VALUES (:portfolio_exposure_pct, :created_at, :updated_at)"
            ),
            {
                "portfolio_exposure_pct": 25.0,
                "created_at": "2024-09-02T00:00:00Z",
                "updated_at": "2024-09-02T00:00:00Z",
            },
        )

    existing_guard = conn.execute(sa.text("SELECT COUNT(*) FROM trade_guard_config"))
    if existing_guard.scalar() == 0:
        leverage_tiers = json.dumps(
            [
                {"leverage": 5, "symbols": ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE"]},
                {"leverage": 3, "symbols": ["SUI", "FARTCOIN", "LTC", "BCH", "XRP"]},
            ]
        )
        conn.execute(
            sa.text(
                "INSERT INTO trade_guard_config "
                "(min_confidence, min_position_size, sl_min_roe, sl_max_roe, "
                "dust_threshold_usd, leverage_tiers, created_at, updated_at) "
                "VALUES (:min_confidence, :min_position_size, :sl_min_roe, :sl_max_roe, "
                ":dust_threshold_usd, :leverage_tiers, :created_at, :updated_at)"
            ),
            {
                "min_confidence": 60.0,
                "min_position_size": 10.0,
                "sl_min_roe": 0.03,
                "sl_max_roe": 0.05,
                "dust_threshold_usd": 15.0,
                "leverage_tiers": leverage_tiers,
                "created_at": "2024-09-02T00:00:00Z",
                "updated_at": "2024-09-02T00:00:00Z",
            },
        )


def downgrade() -> None:
    op.drop_table("trade_guard_config")
    op.drop_table("account_setup")
