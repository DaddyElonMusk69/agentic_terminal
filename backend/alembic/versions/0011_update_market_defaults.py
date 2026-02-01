"""Update monitored defaults for assets and intervals.

Revision ID: 0011_update_market_defaults
Revises: 0010_exchange_account_status
Create Date: 2024-09-09 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0011_update_market_defaults"
down_revision = "0010_exchange_account_status"
branch_labels = None
depends_on = None


DEFAULT_TIMESTAMP = "2024-09-02T00:00:00Z"


def upgrade() -> None:
    conn = op.get_bind()

    existing_assets = conn.execute(sa.text("SELECT COUNT(*) FROM monitored_assets"))
    if existing_assets.scalar() == 0:
        conn.execute(
            sa.text(
                "INSERT INTO monitored_assets (symbol, created_at, updated_at) "
                "VALUES (:symbol, :created_at, :updated_at)"
            ),
            {"symbol": "BTC", "created_at": DEFAULT_TIMESTAMP, "updated_at": DEFAULT_TIMESTAMP},
        )

    existing_coins = conn.execute(sa.text("SELECT symbol FROM monitored_coins"))
    coins = {row[0] for row in existing_coins.fetchall()}
    if not coins:
        conn.execute(
            sa.text(
                "INSERT INTO monitored_coins (symbol, display_order, created_at, updated_at) "
                "VALUES (:symbol, :display_order, :created_at, :updated_at)"
            ),
            {
                "symbol": "BTC",
                "display_order": 1,
                "created_at": DEFAULT_TIMESTAMP,
                "updated_at": DEFAULT_TIMESTAMP,
            },
        )
    elif coins == {"BTC", "ETH", "SOL"}:
        conn.execute(
            sa.text("DELETE FROM monitored_coins WHERE symbol IN ('ETH', 'SOL')")
        )
        conn.execute(
            sa.text("UPDATE monitored_coins SET display_order = 1 WHERE symbol = 'BTC'")
        )

    existing_intervals = conn.execute(sa.text("SELECT interval FROM monitored_intervals"))
    intervals = {row[0] for row in existing_intervals.fetchall()}
    if not intervals:
        conn.execute(
            sa.text(
                "INSERT INTO monitored_intervals (interval, display_order, created_at, updated_at) "
                "VALUES (:interval, :display_order, :created_at, :updated_at)"
            ),
            {
                "interval": "2h",
                "display_order": 1,
                "created_at": DEFAULT_TIMESTAMP,
                "updated_at": DEFAULT_TIMESTAMP,
            },
        )
    elif intervals == {"2h", "4h"}:
        conn.execute(
            sa.text("DELETE FROM monitored_intervals WHERE interval = '4h'")
        )
        conn.execute(
            sa.text("UPDATE monitored_intervals SET display_order = 1 WHERE interval = '2h'")
        )


def downgrade() -> None:
    # No-op: keep user-defined monitored assets/intervals intact.
    pass
