"""Expand alembic version column length.

Revision ID: 0011b_expand_alembic_version
Revises: 0011_update_market_defaults
Create Date: 2024-09-09 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0011b_expand_alembic_version"
down_revision = "0011_update_market_defaults"
branch_labels = None
depends_on = None


def _supports_alter_column() -> bool:
    bind = op.get_bind()
    return bind.dialect.name != "sqlite"


def upgrade() -> None:
    if not _supports_alter_column():
        return
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.String(length=64),
        existing_nullable=False,
    )


def downgrade() -> None:
    if not _supports_alter_column():
        return
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=64),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
