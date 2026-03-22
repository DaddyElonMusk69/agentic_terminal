from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from app.infrastructure.external.codex_cli import execute_codex_cli
from app.infrastructure.external.codex_temp_images import CodexTempImageStore

from app.domain.llm_caller.models import LlmCallRequest, LlmCallResponse


class LlmCallerService:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        codex_cli_path: str = "codex",
        codex_cli_timeout_seconds: int = 180,
        codex_temp_image_path: str = "backend/tmp/codex_images",
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._codex_cli_path = codex_cli_path
        self._codex_cli_timeout_seconds = codex_cli_timeout_seconds
        self._codex_temp_images = CodexTempImageStore(codex_temp_image_path)

    async def call(
        self,
        request: LlmCallRequest,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        protocol: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> LlmCallResponse:
        resolved_protocol = (protocol or "openai").strip().lower()
        if resolved_protocol == "codex_cli":
            return await self._call_codex_cli(request, provider=provider)

        resolved_key = api_key or self._api_key
        resolved_base = (base_url or self._base_url).rstrip("/")
        if not resolved_key:
            raise ValueError("LLM API key is required")

        payload = {
            "model": request.model,
            "messages": _build_openai_messages(request.prompt_text, request.images),
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        start = time.time()
        try:
            import httpx
        except Exception as exc:
            raise RuntimeError("httpx is required for LLM calls") from exc

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{resolved_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {resolved_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()

        latency_ms = (time.time() - start) * 1000.0
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        tokens_used = data.get("usage", {}).get("total_tokens", 0)

        return LlmCallResponse(
            content=content,
            model=request.model,
            tokens_used=tokens_used,
            latency_ms=latency_ms,
            raw_response=data,
        )

    async def _call_codex_cli(
        self,
        request: LlmCallRequest,
        provider: Optional[str] = None,
    ) -> LlmCallResponse:
        image_paths = await self._resolve_codex_image_paths(request.images)

        start = time.time()
        result = await execute_codex_cli(
            prompt_text=request.prompt_text,
            model=request.model,
            reasoning_effort=request.reasoning_effort,
            images=image_paths,
            cli_path=self._codex_cli_path,
            timeout_seconds=self._codex_cli_timeout_seconds,
            cwd=str(Path.cwd()),
        )
        latency_ms = (time.time() - start) * 1000.0

        raw_response = {
            "provider": provider or "codex",
            "protocol": "codex_cli",
            "events": result.events,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "image_paths": image_paths,
        }
        return LlmCallResponse(
            content=result.content,
            model=result.model or request.model,
            tokens_used=result.tokens_used,
            latency_ms=latency_ms,
            raw_response=raw_response,
        )

    async def _resolve_codex_image_paths(self, images: List[Dict[str, Any]]) -> List[str]:
        local_paths = self._codex_temp_images.extract_local_paths(images)
        seen = set(local_paths)
        resolved = list(local_paths)

        for index, image in enumerate(images):
            if not isinstance(image, dict):
                continue
            raw_url = image.get("image_url")
            if not isinstance(raw_url, str) or not raw_url.strip():
                continue
            if self._codex_temp_images.extract_local_paths([{"image_url": raw_url}]):
                continue

            try:
                image_bytes, suffix = await _read_image_bytes(raw_url)
            except Exception as exc:
                raise RuntimeError(
                    f"codex image fetch failed for {raw_url}: {exc.__class__.__name__}: {exc}"
                ) from exc
            name = f"codex_input_{index}_{int(time.time())}"
            stored_path = self._codex_temp_images.save_bytes(image_bytes, name=name, suffix=suffix)
            if stored_path in seen:
                continue
            seen.add(stored_path)
            resolved.append(stored_path)

        return resolved


def _build_openai_messages(prompt_text: str, images: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not images:
        return [{"role": "user", "content": prompt_text}]

    content: List[Dict[str, Any]] = []
    if prompt_text:
        content.append({"type": "text", "text": prompt_text})

    for image in images:
        url = image.get("image_url") if isinstance(image, dict) else None
        if not url:
            continue
        content.append({"type": "image_url", "image_url": {"url": url}})

    return [{"role": "user", "content": content}]


def extract_chart_images(prompt_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    images: List[Dict[str, Any]] = []
    chart_snapshots = prompt_data.get("chart_snapshots")
    if isinstance(chart_snapshots, list):
        for item in chart_snapshots:
            if isinstance(item, dict) and item.get("type") == "input_image":
                images.append(
                    {
                        "image_url": item.get("image_url"),
                        "ticker": item.get("ticker"),
                        "interval": item.get("interval"),
                    }
                )
    return images


async def _read_image_bytes(raw_url: str) -> tuple[bytes, str]:
    parsed = urlparse(raw_url)
    if parsed.scheme in ("http", "https"):
        try:
            import httpx
        except Exception as exc:
            raise RuntimeError("httpx is required to fetch remote codex images") from exc
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(raw_url)
            response.raise_for_status()
            data = response.content
            content_type = response.headers.get("Content-Type")
        suffix = _guess_image_suffix(raw_url=raw_url, content_type=content_type, data=data)
        return data, suffix

    if parsed.scheme == "file":
        local_path = Path(parsed.path)
    else:
        local_path = Path(raw_url)
    if not local_path.exists() or not local_path.is_file():
        raise ValueError(f"codex image path does not exist: {raw_url}")

    data = local_path.read_bytes()
    suffix = _guess_image_suffix(raw_url=str(local_path), content_type=None, data=data)
    return data, suffix


def _guess_image_suffix(raw_url: str, content_type: Optional[str], data: bytes) -> str:
    parsed_suffix = Path(urlparse(raw_url).path).suffix.lower()
    if parsed_suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
        return parsed_suffix

    if content_type:
        lowered = content_type.lower()
        mapping = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/webp": ".webp",
            "image/gif": ".gif",
            "image/bmp": ".bmp",
        }
        if lowered in mapping:
            return mapping[lowered]

    detected = _detect_image_suffix(data)
    if detected:
        return detected
    return ".png"


def _detect_image_suffix(data: bytes) -> Optional[str]:
    if not data:
        return None
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8"):
        return ".jpg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return ".gif"
    if data.startswith(b"BM"):
        return ".bmp"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None
