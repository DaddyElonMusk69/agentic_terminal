"""Create prompt build requests queue table.

Revision ID: 0006_prompt_build_req
Revises: 0005_create_prompt_templates
Create Date: 2024-09-02 00:00:05.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "0006_prompt_build_req"
down_revision = "0005_create_prompt_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompt_build_requests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("prompt_build_requests")
