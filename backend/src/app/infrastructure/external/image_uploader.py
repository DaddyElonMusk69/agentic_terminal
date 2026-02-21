from __future__ import annotations

import asyncio
import base64
import random
from pathlib import Path
from typing import Optional

from app.domain.image_uploader.models import ImageUploaderConfig
from app.domain.prompt_builder.interfaces import ImageUploader

_UPLOAD_RETRY_COUNT = 3
_UPLOAD_RETRY_BASE_DELAY = 0.5
_UPLOAD_RETRY_MAX_DELAY = 4.0
_UPLOAD_RETRY_JITTER = 0.3
_UPLOAD_THROTTLE_DELAY = 0.1
_RETRYABLE_STATUSES = {408, 425, 429, 500, 502, 503, 504}


class FileSystemImageUploader:
    def __init__(self, base_path: Path, base_url: Optional[str] = None) -> None:
        self._base_path = base_path
        self._base_url = base_url or ""

    async def upload(self, image_bytes: bytes, name: str) -> Optional[str]:
        if not image_bytes:
            return None

        self._base_path.mkdir(parents=True, exist_ok=True)
        filename = f"{name}.png"
        path = self._base_path / filename
        path.write_bytes(image_bytes)

        if self._base_url:
            return f"{self._base_url.rstrip('/')}/{filename}"
        return str(path)


class ImgBBImageUploader:
    def __init__(self, api_key: str, api_url: str = "https://api.imgbb.com/1/upload") -> None:
        self._api_key = api_key
        self._api_url = api_url
        self._client = None

    async def upload(self, image_bytes: bytes, name: str) -> Optional[str]:
        if not image_bytes or not self._api_key:
            return None

        try:
            import httpx
        except Exception:
            return None

        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)

        payload = {
            "key": self._api_key,
            "image": base64.b64encode(image_bytes).decode("ascii"),
        }
        if name:
            payload["name"] = name

        response = await _post_with_retry(self._client, self._api_url, payload)
        data = response.json()
        return _extract_image_url(data)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


class FreeImageHostUploader:
    def __init__(self, api_key: str, api_url: str = "https://freeimage.host/api/1/upload") -> None:
        self._api_key = api_key
        self._api_url = api_url
        self._client = None

    async def upload(self, image_bytes: bytes, name: str) -> Optional[str]:
        if not image_bytes or not self._api_key:
            return None

        try:
            import httpx
        except Exception:
            return None

        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)

        payload = {
            "key": self._api_key,
            "action": "upload",
            "source": base64.b64encode(image_bytes).decode("ascii"),
            "format": "json",
        }
        if name:
            payload["name"] = name

        import random
        fake_ip = f"{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}"
        headers = {
            "X-Forwarded-For": fake_ip,
            "Client-IP": fake_ip,
        }

        response = await _post_with_retry(self._client, self._api_url, payload, headers=headers)
        data = response.json()
        return _extract_image_url(data)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def build_image_uploader(settings, config: ImageUploaderConfig | None = None) -> ImageUploader:
    uploader = str(getattr(settings, "prompt_image_uploader", "filesystem")).lower()
    api_key_override = None
    if config is not None:
        uploader = config.provider.lower()
        api_key_override = config.api_key

    if uploader == "imgbb":
        api_key = api_key_override or getattr(settings, "prompt_image_imgbb_api_key", "") or ""
        api_url = getattr(settings, "prompt_image_imgbb_api_url", "") or "https://api.imgbb.com/1/upload"
        if not api_key:
            raise ValueError("BACKEND_PROMPT_IMAGE_IMGBB_API_KEY is required for ImgBB uploads")
        return ImgBBImageUploader(api_key=api_key, api_url=api_url)

    if uploader in ("freeimage", "freeimage.host"):
        api_key = api_key_override or getattr(settings, "prompt_image_freeimage_api_key", "") or ""
        api_url = getattr(settings, "prompt_image_freeimage_api_url", "") or "https://freeimage.host/api/1/upload"
        if not api_key:
            raise ValueError("BACKEND_PROMPT_IMAGE_FREEIMAGE_API_KEY is required for freeimage.host uploads")
        return FreeImageHostUploader(api_key=api_key, api_url=api_url)

    base_path = Path(getattr(settings, "prompt_image_store_path", "backend/tmp/prompt_images"))
    base_url = getattr(settings, "prompt_image_base_url", "") or ""
    return FileSystemImageUploader(base_path=base_path, base_url=base_url)


def _extract_image_url(payload: dict) -> Optional[str]:
    if not isinstance(payload, dict):
        return None

    data = payload.get("data") or payload
    if isinstance(data, dict):
        url = data.get("url")
        if url:
            return url
        image = data.get("image")
        if isinstance(image, dict) and image.get("url"):
            return image["url"]

    image = payload.get("image")
    if isinstance(image, dict) and image.get("url"):
        return image["url"]

    return None


async def _post_with_retry(client, url: str, payload: dict, headers: dict | None = None):
    max_attempts = max(1, _UPLOAD_RETRY_COUNT)
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        if _UPLOAD_THROTTLE_DELAY > 0:
            await asyncio.sleep(_UPLOAD_THROTTLE_DELAY)
        try:
            response = await client.post(url, data=payload, headers=headers)
            if response.status_code in _RETRYABLE_STATUSES and attempt < max_attempts:
                await _sleep_backoff(attempt)
                continue
            response.raise_for_status()
            return response
        except Exception as exc:  # Let httpx raise the concrete error type.
            last_exc = exc
            response = getattr(exc, "response", None)
            status_code = getattr(response, "status_code", None)
            if status_code is not None and status_code not in _RETRYABLE_STATUSES:
                raise
            if attempt < max_attempts:
                await _sleep_backoff(attempt)
                continue
            raise
    if last_exc:
        raise last_exc
    raise RuntimeError("Image upload failed")


async def _sleep_backoff(attempt: int) -> None:
    delay = _UPLOAD_RETRY_BASE_DELAY * (2 ** (attempt - 1))
    delay = min(delay, _UPLOAD_RETRY_MAX_DELAY)
    delay += random.uniform(0, _UPLOAD_RETRY_JITTER)
    await asyncio.sleep(delay)
