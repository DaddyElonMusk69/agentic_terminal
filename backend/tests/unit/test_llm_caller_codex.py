from pathlib import Path

import pytest

from app.application.llm_caller.service import LlmCallerService
from app.domain.llm_caller.models import LlmCallRequest
from app.infrastructure.external.codex_cli import CodexExecResult


@pytest.mark.asyncio
async def test_codex_protocol_uses_local_images(monkeypatch, tmp_path: Path):
    captured = {}

    async def fake_execute_codex_cli(**kwargs):
        captured.update(kwargs)
        return CodexExecResult(
            content='JSON_ARRAY [{"action":"HOLD","symbol":"BTC"}]',
            model="gpt-5.3-codex",
            tokens_used=123,
            events=[{"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 20}}],
            stdout='{"type":"turn.completed"}',
            stderr="",
        )

    monkeypatch.setattr("app.application.llm_caller.service.execute_codex_cli", fake_execute_codex_cli)

    service = LlmCallerService(
        api_key="",
        base_url="https://api.example.com/v1",
        codex_temp_image_path=str(tmp_path),
    )
    local_image = service._codex_temp_images.save_png(b"image", "local_chart")
    request = LlmCallRequest(
        prompt_text="analyze",
        images=[{"image_url": local_image}],
        model="gpt-5.3-codex",
        temperature=0.0,
        max_tokens=128,
    )

    response = await service.call(request, protocol="codex_cli", provider="codex")

    assert captured["images"] == [local_image]
    assert captured["reasoning_effort"] is None
    assert response.model == "gpt-5.3-codex"
    assert response.tokens_used == 123
    assert response.raw_response["protocol"] == "codex_cli"
    assert response.raw_response["image_paths"] == [local_image]


@pytest.mark.asyncio
async def test_codex_protocol_downloads_non_local_images(monkeypatch, tmp_path: Path):
    captured = {}

    async def fake_execute_codex_cli(**kwargs):
        captured.update(kwargs)
        return CodexExecResult(
            content="ok",
            model="gpt-5.3-codex",
            tokens_used=1,
            events=[],
            stdout="{}",
            stderr="",
        )

    async def fake_read_image_bytes(raw_url: str):
        assert raw_url == "https://example.com/image.png"
        return b"remote-bytes", ".png"

    monkeypatch.setattr("app.application.llm_caller.service.execute_codex_cli", fake_execute_codex_cli)
    monkeypatch.setattr("app.application.llm_caller.service._read_image_bytes", fake_read_image_bytes)

    service = LlmCallerService(
        api_key="",
        base_url="https://api.example.com/v1",
        codex_temp_image_path=str(tmp_path),
    )
    request = LlmCallRequest(
        prompt_text="analyze",
        images=[{"image_url": "https://example.com/image.png"}],
        model="gpt-5.3-codex",
        temperature=0.0,
        max_tokens=128,
    )

    response = await service.call(request, protocol="codex_cli", provider="codex")

    assert len(captured["images"]) == 1
    assert captured["reasoning_effort"] is None
    saved_path = Path(captured["images"][0])
    assert saved_path.exists()
    assert str(saved_path).startswith(str(tmp_path))
    assert response.raw_response["image_paths"] == [str(saved_path)]


@pytest.mark.asyncio
async def test_codex_protocol_passes_reasoning_effort(monkeypatch, tmp_path: Path):
    captured = {}

    async def fake_execute_codex_cli(**kwargs):
        captured.update(kwargs)
        return CodexExecResult(
            content="ok",
            model="gpt-5.4",
            tokens_used=1,
            events=[],
            stdout="{}",
            stderr="",
        )

    monkeypatch.setattr("app.application.llm_caller.service.execute_codex_cli", fake_execute_codex_cli)

    service = LlmCallerService(
        api_key="",
        base_url="https://api.example.com/v1",
        codex_temp_image_path=str(tmp_path),
    )
    request = LlmCallRequest(
        prompt_text="analyze",
        images=[],
        model="gpt-5.4",
        temperature=0.0,
        max_tokens=128,
        reasoning_effort="xhigh",
    )

    await service.call(request, protocol="codex_cli", provider="codex")

    assert captured["reasoning_effort"] == "xhigh"
