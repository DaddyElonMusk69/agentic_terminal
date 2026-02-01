"""Create EMA scanner config and shared monitoring tables.

Revision ID: 0003_create_ema_scanner_config
Revises: 0002_create_outbox_messages
Create Date: 2024-09-02 00:00:02.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0003_create_ema_scanner_config"
down_revision = "0002_create_outbox_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monitored_coins",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(length=20), nullable=False, unique=True),
        sa.Column("display_order", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "monitored_assets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(length=50), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "monitored_intervals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("interval", sa.String(length=10), nullable=False, unique=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "ema_scanner_config",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tolerance_pct", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("tolerance_pct >= 0.05", name="ck_ema_tolerance_min"),
        sa.CheckConstraint("tolerance_pct <= 2.0", name="ck_ema_tolerance_max"),
    )

    op.create_table(
        "ema_scanner_lines",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("length", sa.Integer(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    conn = op.get_bind()

    existing_config = conn.execute(sa.text("SELECT COUNT(*) FROM ema_scanner_config"))
    if existing_config.scalar() == 0:
        conn.execute(
            sa.text(
                "INSERT INTO ema_scanner_config (tolerance_pct, created_at, updated_at) "
                "VALUES (:tolerance, :created_at, :updated_at)"
            ),
            {
                "tolerance": 0.2,
                "created_at": "2024-09-02T00:00:00Z",
                "updated_at": "2024-09-02T00:00:00Z",
            },
        )

    existing_lines = conn.execute(sa.text("SELECT COUNT(*) FROM ema_scanner_lines"))
    if existing_lines.scalar() == 0:
        conn.execute(
            sa.text(
                "INSERT INTO ema_scanner_lines (length, created_at, updated_at) "
                "VALUES (:length, :created_at, :updated_at)"
            ),
            [
                {"length": 144, "created_at": "2024-09-02T00:00:00Z", "updated_at": "2024-09-02T00:00:00Z"},
                {"length": 169, "created_at": "2024-09-02T00:00:00Z", "updated_at": "2024-09-02T00:00:00Z"},
            ],
        )

    existing_coins = conn.execute(sa.text("SELECT COUNT(*) FROM monitored_coins"))
    if existing_coins.scalar() == 0:
        conn.execute(
            sa.text(
                "INSERT INTO monitored_coins (symbol, display_order, created_at, updated_at) "
                "VALUES (:symbol, :display_order, :created_at, :updated_at)"
            ),
            [
                {"symbol": "BTC", "display_order": 1, "created_at": "2024-09-02T00:00:00Z", "updated_at": "2024-09-02T00:00:00Z"},
                {"symbol": "ETH", "display_order": 2, "created_at": "2024-09-02T00:00:00Z", "updated_at": "2024-09-02T00:00:00Z"},
                {"symbol": "SOL", "display_order": 3, "created_at": "2024-09-02T00:00:00Z", "updated_at": "2024-09-02T00:00:00Z"},
            ],
        )

    existing_intervals = conn.execute(sa.text("SELECT COUNT(*) FROM monitored_intervals"))
    if existing_intervals.scalar() == 0:
        conn.execute(
            sa.text(
                "INSERT INTO monitored_intervals (interval, display_order, created_at, updated_at) "
                "VALUES (:interval, :display_order, :created_at, :updated_at)"
            ),
            [
                {"interval": "2h", "display_order": 1, "created_at": "2024-09-02T00:00:00Z", "updated_at": "2024-09-02T00:00:00Z"},
                {"interval": "4h", "display_order": 2, "created_at": "2024-09-02T00:00:00Z", "updated_at": "2024-09-02T00:00:00Z"},
            ],
        )


def downgrade() -> None:
    op.drop_table("ema_scanner_lines")
    op.drop_table("ema_scanner_config")
    op.drop_table("monitored_intervals")
    op.drop_table("monitored_assets")
    op.drop_table("monitored_coins")
