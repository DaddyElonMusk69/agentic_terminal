import os
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from app.settings import get_settings


def test_ema_state_manager_defaults_seeded(tmp_path):
    db_path = tmp_path / "ema_state_defaults.db"
    os.environ["BACKEND_DATABASE_URL"] = f"sqlite:///{db_path}"
    get_settings.cache_clear()

    backend_root = Path(__file__).resolve().parents[2]
    alembic_cfg = Config(str(backend_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_root / "alembic"))

    command.upgrade(alembic_cfg, "head")

    engine = sa.create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT min_resonance, ema_resonance_cooldown_seconds, "
                "bb_rejection_cooldown_seconds, bb_exit_warning_cooldown_seconds, "
                "position_check_interval_seconds, bb_rejection_min_touches, "
                "bb_htf_min_interval_minutes "
                "FROM ema_state_manager_config"
            )
        ).fetchall()

        assert rows == [(2, 600, 1200, 600, 1800, 10, 480)]
