"""Create outbox messages table.

Revision ID: 0002_create_outbox_messages
Revises: 0001_create_exchange_accounts
Create Date: 2024-09-02 00:00:01.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0002_create_outbox_messages"
down_revision = "0001_create_exchange_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outbox_messages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("message_type", sa.String(length=20), nullable=False),
        sa.Column("topic", sa.String(length=200), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("outbox_messages")
