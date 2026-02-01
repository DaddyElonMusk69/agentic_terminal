import os
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from app.settings import get_settings


def test_ema_scanner_defaults_seeded(tmp_path):
    db_path = tmp_path / "ema_defaults.db"
    os.environ["BACKEND_DATABASE_URL"] = f"sqlite:///{db_path}"
    get_settings.cache_clear()

    backend_root = Path(__file__).resolve().parents[2]
    alembic_cfg = Config(str(backend_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_root / "alembic"))

    command.upgrade(alembic_cfg, "head")

    engine = sa.create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        tolerance = conn.execute(sa.text("SELECT tolerance_pct FROM ema_scanner_config"))
        tolerance_values = [row[0] for row in tolerance.fetchall()]
        assert tolerance_values == [0.2]

        lines = conn.execute(sa.text("SELECT length FROM ema_scanner_lines ORDER BY length"))
        assert [row[0] for row in lines.fetchall()] == [144, 169]

        coins = conn.execute(sa.text("SELECT symbol FROM monitored_coins ORDER BY display_order"))
        assert [row[0] for row in coins.fetchall()] == ["BTC", "ETH", "SOL"]

        intervals = conn.execute(sa.text("SELECT interval FROM monitored_intervals ORDER BY display_order"))
        assert [row[0] for row in intervals.fetchall()] == ["2h", "4h"]

        assets = conn.execute(sa.text("SELECT symbol FROM monitored_assets"))
        assert assets.fetchall() == []
