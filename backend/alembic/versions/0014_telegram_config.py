"""Create telegram config table.

Revision ID: 0014_telegram_config
Revises: 0013_create_scan_results
Create Date: 2024-09-12 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0014_telegram_config"
down_revision = "0013_create_scan_results"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telegram_config",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("bot_token_encrypted", sa.Text(), nullable=True),
        sa.Column("chat_id", sa.Text(), nullable=True),
        sa.Column("recipients", sa.JSON(), nullable=True),
        sa.Column("notifications", sa.JSON(), nullable=True),
        sa.Column(
            "parse_mode",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'Markdown'"),
        ),
        sa.Column(
            "disable_notification",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("telegram_config")
