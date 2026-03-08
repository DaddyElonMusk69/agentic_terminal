from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Dict, Iterable, List, Sequence
from urllib.parse import unquote, urlparse
from uuid import uuid4


def _backend_root() -> Path:
    # backend/src/app/infrastructure/external/codex_temp_images.py -> backend/
    return Path(__file__).resolve().parents[4]


def _resolve_base_path(path: str | Path) -> tuple[Path, tuple[Path, ...]]:
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve(), tuple()

    backend_root = _backend_root()
    parts = candidate.parts
    has_legacy_prefix = bool(parts) and parts[0] == backend_root.name

    if has_legacy_prefix:
        trimmed = Path(*parts[1:]) if len(parts) > 1 else Path()
        canonical = (backend_root / trimmed).resolve()
        legacy = (backend_root / candidate).resolve()
        if legacy != canonical:
            return canonical, (legacy,)
        return canonical, tuple()

    return (backend_root / candidate).resolve(), tuple()


def _safe_stem(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(name or ""))
    cleaned = cleaned.strip("._")
    return cleaned or "image"


class CodexTempImageStore:
    def __init__(self, base_path: str | Path) -> None:
        resolved_base, legacy_paths = _resolve_base_path(base_path)
        self._base_path = resolved_base
        # Keep compatibility with earlier cwd-relative "backend/..." resolution.
        self._managed_roots = tuple([resolved_base, *legacy_paths])

    @property
    def base_path(self) -> Path:
        return self._base_path

    @property
    def managed_roots(self) -> tuple[Path, ...]:
        return self._managed_roots

    def save_png(self, image_bytes: bytes, name: str) -> str:
        return self.save_bytes(image_bytes, name=name, suffix=".png")

    def save_bytes(self, image_bytes: bytes, name: str, suffix: str = ".png") -> str:
        if not image_bytes:
            raise ValueError("image_bytes is required")

        suffix_value = suffix if suffix.startswith(".") else f".{suffix}"
        stem = _safe_stem(name)
        self._base_path.mkdir(parents=True, exist_ok=True)

        candidate = self._base_path / f"{stem}{suffix_value}"
        if candidate.exists():
            candidate = self._base_path / f"{stem}_{uuid4().hex}{suffix_value}"

        candidate.write_bytes(image_bytes)
        return str(candidate.resolve())

    def extract_local_paths(self, images: Sequence[Dict[str, object]]) -> List[str]:
        local_paths: List[str] = []
        seen = set()

        for image in images:
            if not isinstance(image, dict):
                continue
            raw_url = image.get("image_url")
            if not isinstance(raw_url, str) or not raw_url.strip():
                continue

            parsed = urlparse(raw_url)
            if parsed.scheme in ("http", "https"):
                continue
            if parsed.scheme == "file":
                candidate = Path(unquote(parsed.path))
            else:
                candidate = Path(raw_url)

            resolved = self._resolve_candidate(candidate)
            if not resolved or not self._is_within_base(resolved):
                continue

            value = str(resolved)
            if value in seen:
                continue
            seen.add(value)
            local_paths.append(value)

        return local_paths

    def delete_paths(self, paths: Iterable[str]) -> int:
        deleted = 0
        seen = set()
        for raw_path in paths:
            if not raw_path:
                continue
            candidate = Path(str(raw_path))
            resolved = self._resolve_candidate(candidate)
            if not resolved or not self._is_within_base(resolved):
                continue

            value = str(resolved)
            if value in seen:
                continue
            seen.add(value)

            if not resolved.exists() or not resolved.is_file():
                continue
            try:
                resolved.unlink()
                deleted += 1
            except OSError:
                continue
        return deleted

    def sweep_expired(self, ttl_minutes: int) -> int:
        ttl_seconds = max(0, int(ttl_minutes)) * 60
        cutoff_ts = time.time() - ttl_seconds
        deleted = 0
        seen: set[str] = set()

        for root in self._managed_roots:
            if not root.exists():
                continue

            for candidate in root.rglob("*"):
                if not candidate.is_file():
                    continue
                resolved = self._resolve_candidate(candidate)
                if not resolved or not self._is_within_base(resolved):
                    continue

                key = str(resolved)
                if key in seen:
                    continue
                seen.add(key)

                try:
                    modified_at = resolved.stat().st_mtime
                except OSError:
                    continue
                if modified_at > cutoff_ts:
                    continue
                try:
                    resolved.unlink()
                    deleted += 1
                except OSError:
                    continue

        return deleted

    def _resolve_candidate(self, path: Path) -> Path | None:
        try:
            return path.expanduser().resolve()
        except OSError:
            return None

    def _is_within_base(self, path: Path) -> bool:
        for root in self._managed_roots:
            try:
                path.relative_to(root)
                return True
            except ValueError:
                continue
        return False
