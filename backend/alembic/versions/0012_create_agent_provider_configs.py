"""Create AI provider config table.

Revision ID: 0012_create_agent_provider_configs
Revises: 0011b_expand_alembic_version
Create Date: 2024-09-09 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0012_create_agent_provider_configs"
down_revision = "0011b_expand_alembic_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_provider_configs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(length=50), nullable=False, unique=True),
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("default_model", sa.String(length=120), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("settings", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("agent_provider_configs")
