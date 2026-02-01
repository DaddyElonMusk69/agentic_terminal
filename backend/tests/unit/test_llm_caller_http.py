import json

import httpx
import pytest

from app.application.llm_caller.service import LlmCallerService
from app.domain.llm_caller.models import LlmCallRequest


@pytest.mark.asyncio
async def test_llm_caller_sends_multimodal_payload(monkeypatch):
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        payload = json.loads(request.content)
        assert payload["model"] == "gpt-test"
        assert payload["temperature"] == 0.25
        assert payload["max_tokens"] == 120

        messages = payload["messages"]
        assert messages[0]["role"] == "user"
        content = messages[0]["content"]
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "hello"
        assert content[1]["type"] == "image_url"
        assert content[1]["image_url"]["url"] == "https://example.com/chart.png"

        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "JSON_ARRAY []"}}],
                "usage": {"total_tokens": 12},
            },
        )

    transport = httpx.MockTransport(handler)

    class PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs) -> None:
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", PatchedAsyncClient)

    service = LlmCallerService(api_key="key", base_url="https://api.example.com/v1/")
    response = await service.call(
        LlmCallRequest(
            prompt_text="hello",
            images=[{"image_url": "https://example.com/chart.png"}],
            model="gpt-test",
            temperature=0.25,
            max_tokens=120,
        )
    )

    assert response.content == "JSON_ARRAY []"
    assert response.tokens_used == 12
    assert len(captured) == 1
    assert str(captured[0].url) == "https://api.example.com/v1/chat/completions"


@pytest.mark.asyncio
async def test_llm_caller_sends_text_only_payload(monkeypatch):
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        payload = json.loads(request.content)
        assert payload["messages"][0]["content"] == "ping"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}], "usage": {"total_tokens": 1}},
        )

    transport = httpx.MockTransport(handler)

    class PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs) -> None:
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", PatchedAsyncClient)

    service = LlmCallerService(api_key="key", base_url="https://api.example.com/v1")
    response = await service.call(
        LlmCallRequest(
            prompt_text="ping",
            images=[],
            model="gpt-test",
            temperature=0.0,
            max_tokens=None,
        )
    )

    assert response.content == "ok"
    assert len(captured) == 1
