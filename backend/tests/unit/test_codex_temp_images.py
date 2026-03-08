import os
import time
from pathlib import Path

import app.infrastructure.external.codex_temp_images as codex_temp_images_module
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


def test_relative_backend_prefixed_path_is_stable_across_cwd(monkeypatch, tmp_path: Path):
    backend_root = tmp_path / "backend"
    backend_root.mkdir(parents=True, exist_ok=True)
    workspace_root = backend_root.parent
    expected = (backend_root / "tmp/codex_images").resolve()
    monkeypatch.setattr(codex_temp_images_module, "_backend_root", lambda: backend_root)

    monkeypatch.chdir(workspace_root)
    from_workspace = CodexTempImageStore("backend/tmp/codex_images")

    monkeypatch.chdir(backend_root)
    from_backend = CodexTempImageStore("backend/tmp/codex_images")

    assert from_workspace.base_path == expected
    assert from_backend.base_path == expected


def test_sweep_expired_cleans_legacy_backend_prefixed_directory(monkeypatch, tmp_path: Path):
    backend_root = tmp_path / "backend"
    backend_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(codex_temp_images_module, "_backend_root", lambda: backend_root)

    legacy_dir = backend_root / "backend/tmp/codex_images"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    legacy_file = legacy_dir / "legacy_stale.png"
    legacy_file.write_bytes(b"stale")
    old_ts = time.time() - (4 * 3600)
    os.utime(legacy_file, (old_ts, old_ts))

    try:
        monkeypatch.chdir(backend_root)
        store = CodexTempImageStore("backend/tmp/codex_images")
        removed = store.sweep_expired(ttl_minutes=60)
        assert removed >= 1
        assert not legacy_file.exists()
    finally:
        if legacy_file.exists():
            legacy_file.unlink()
