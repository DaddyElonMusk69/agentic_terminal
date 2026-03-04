import os
import time
from pathlib import Path

from app.infrastructure.external.codex_temp_images import CodexTempImageStore


def test_save_and_extract_local_paths(tmp_path: Path):
    store = CodexTempImageStore(tmp_path)
    saved = store.save_png(b"payload", "btc_1h")

    assert Path(saved).exists()
    extracted = store.extract_local_paths(
        [
            {"image_url": saved},
            {"image_url": "https://example.com/chart.png"},
        ]
    )
    assert extracted == [saved]


def test_delete_paths_only_removes_files_within_store(tmp_path: Path):
    store = CodexTempImageStore(tmp_path)
    managed = store.save_png(b"managed", "managed")

    outside = tmp_path.parent / "outside.png"
    outside.write_bytes(b"outside")

    deleted = store.delete_paths([managed, str(outside)])
    assert deleted == 1
    assert not Path(managed).exists()
    assert outside.exists()


def test_sweep_expired_removes_old_files(tmp_path: Path):
    store = CodexTempImageStore(tmp_path)
    old_path = Path(store.save_png(b"old", "old"))
    fresh_path = Path(store.save_png(b"fresh", "fresh"))

    old_ts = time.time() - (3 * 3600)
    os.utime(old_path, (old_ts, old_ts))

    removed = store.sweep_expired(ttl_minutes=60)
    assert removed == 1
    assert not old_path.exists()
    assert fresh_path.exists()
