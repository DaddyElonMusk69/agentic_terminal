"""Create image uploader config table.

Revision ID: 0007_image_uploader_cfg
Revises: 0006_prompt_build_req
Create Date: 2024-09-02 00:00:06.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "0007_image_uploader_cfg"
down_revision = "0006_prompt_build_req"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "image_uploader_config",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("api_key", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("image_uploader_config")
