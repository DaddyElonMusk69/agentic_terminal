"""Create prompt templates table.

Revision ID: 0005_create_prompt_templates
Revises: 0004_ema_state_mgr
Create Date: 2024-09-02 00:00:04.000000
"""

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0005_create_prompt_templates"
down_revision = "0004_ema_state_mgr"
branch_labels = None
depends_on = None


SEED_TIMESTAMP = datetime(2024, 9, 2, tzinfo=timezone.utc)


def upgrade() -> None:
    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("intro", sa.Text(), nullable=False),
        sa.Column("response_format", sa.Text(), nullable=False),
        sa.Column("quant_fields", sa.JSON(), nullable=True),
        sa.Column("chart_defaults", sa.JSON(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    conn = op.get_bind()
    existing = conn.execute(sa.text("SELECT COUNT(*) FROM prompt_templates"))
    if existing.scalar() == 0:
        prompt_templates = sa.table(
            "prompt_templates",
            sa.column("name", sa.String),
            sa.column("intro", sa.Text),
            sa.column("response_format", sa.Text),
            sa.column("quant_fields", sa.JSON),
            sa.column("chart_defaults", sa.JSON),
            sa.column("is_default", sa.Boolean),
            sa.column("created_at", sa.DateTime(timezone=True)),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        )

        intro = (
            "You are a crypto market analyst. Use the provided quantitative data "
            "and charts for the requested ticker and intervals. Be concise and "
            "reference numbers from the data."
        )
        response_format = (
            "Return JSON only:\n"
            "{\n"
            '  "verdict": "open_long|open_short|hold|reduce|close",\n'
            '  "confidence": 0-100,\n'
            '  "rationale": "...",\n'
            '  "key_levels": {\n'
            '    "entry": null,\n'
            '    "stop_loss": null,\n'
            '    "take_profit": null\n'
            "  }\n"
            "}"
        )

        quant_fields = [
            "price_current",
            "price_slope",
            "price_slope_z",
            "oi_current",
            "cvd_current",
            "cvd_slope",
            "cvd_slope_z",
            "funding_rate",
            "order_book",
            "vwap",
            "atr",
            "netflow",
            "anomalies",
        ]
        chart_defaults = {"candles": 50, "overlays": ["ema", "bb"]}

        conn.execute(
            prompt_templates.insert(),
            {
                "name": "default",
                "intro": intro,
                "response_format": response_format,
                "quant_fields": quant_fields,
                "chart_defaults": chart_defaults,
                "is_default": True,
                "created_at": SEED_TIMESTAMP,
                "updated_at": SEED_TIMESTAMP,
            },
        )


def downgrade() -> None:
    op.drop_table("prompt_templates")
