"""Add exchange account validation metadata and agent key.

Revision ID: 0010_exchange_account_status
Revises: 0009_automation_queues
Create Date: 2026-01-28 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0010_exchange_account_status"
down_revision = "0009_automation_queues"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "exchange_accounts",
        sa.Column("wallet_address", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "exchange_accounts",
        sa.Column(
            "validation_status",
            sa.String(length=20),
            nullable=False,
            server_default="unvalidated",
        ),
    )
    op.add_column(
        "exchange_accounts",
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "exchange_accounts",
        sa.Column("validation_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "exchange_credentials",
        sa.Column("agent_key_encrypted", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("exchange_credentials", "agent_key_encrypted")
    op.drop_column("exchange_accounts", "validation_error")
    op.drop_column("exchange_accounts", "last_validated_at")
    op.drop_column("exchange_accounts", "validation_status")
    op.drop_column("exchange_accounts", "wallet_address")
