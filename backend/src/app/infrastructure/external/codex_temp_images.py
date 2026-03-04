from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Dict, Iterable, List, Sequence
from urllib.parse import unquote, urlparse
from uuid import uuid4


def _resolve_base_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (Path.cwd() / candidate).resolve()


def _safe_stem(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(name or ""))
    cleaned = cleaned.strip("._")
    return cleaned or "image"


class CodexTempImageStore:
    def __init__(self, base_path: str | Path) -> None:
        self._base_path = _resolve_base_path(base_path)

    @property
    def base_path(self) -> Path:
        return self._base_path

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
        if not self._base_path.exists():
            return 0
        ttl_seconds = max(0, int(ttl_minutes)) * 60
        cutoff_ts = time.time() - ttl_seconds
        deleted = 0

        for candidate in self._base_path.rglob("*"):
            if not candidate.is_file():
                continue
            resolved = self._resolve_candidate(candidate)
            if not resolved or not self._is_within_base(resolved):
                continue
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
        try:
            path.relative_to(self._base_path)
            return True
        except ValueError:
            return False
