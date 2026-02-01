from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from app.domain.llm_caller.models import LlmCallRequest, LlmCallResponse


class LlmCallerService:
    def __init__(self, api_key: str, base_url: str) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    async def call(
        self,
        request: LlmCallRequest,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> LlmCallResponse:
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
