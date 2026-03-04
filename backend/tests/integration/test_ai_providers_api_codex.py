import pytest

from app.domain.ai_providers.models import ProviderInfo, ProviderValidationResult


class StubAiProviderService:
    def __init__(self) -> None:
        self.validate_calls: list[dict] = []

    async def list_providers(self):
        return [
            ProviderInfo(
                name="codex",
                models=["gpt-5.3-codex", "gpt-5-codex"],
                configured=True,
                is_enabled=True,
                default_model="gpt-5.3-codex",
                settings={"display_name": "Codex CLI", "protocol": "codex_cli"},
            )
        ]

    async def list_models(self, provider: str):
        assert provider == "codex"
        return ["gpt-5.3-codex", "gpt-5-codex", "gpt-5.1-codex"]

    async def validate_provider(
        self,
        provider: str,
        api_key: str | None,
        api_key_provided: bool,
        model: str | None,
    ):
        self.validate_calls.append(
            {
                "provider": provider,
                "api_key": api_key,
                "api_key_provided": api_key_provided,
                "model": model,
            }
        )
        return ProviderValidationResult(
            provider=provider,
            model=model or "gpt-5.3-codex",
            latency_ms=12.5,
            valid=True,
        )


@pytest.mark.asyncio
async def test_list_providers_includes_codex(client, monkeypatch):
    service = StubAiProviderService()
    monkeypatch.setattr("app.api.v1.ai_providers.get_ai_provider_service", lambda: service)

    response = await client.get("/api/v1/ai/providers")

    assert response.status_code == 200
    payload = response.json()
    codex = next(item for item in payload["data"] if item["name"] == "codex")
    assert codex["configured"] is True
    assert codex["settings"]["protocol"] == "codex_cli"


@pytest.mark.asyncio
async def test_list_models_for_codex(client, monkeypatch):
    service = StubAiProviderService()
    monkeypatch.setattr("app.api.v1.ai_providers.get_ai_provider_service", lambda: service)

    response = await client.get("/api/v1/ai/providers/codex/models")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["provider"] == "codex"
    assert "gpt-5.3-codex" in payload["models"]


@pytest.mark.asyncio
async def test_validate_codex_allows_empty_api_key(client, monkeypatch):
    service = StubAiProviderService()
    monkeypatch.setattr("app.api.v1.ai_providers.get_ai_provider_service", lambda: service)

    response = await client.post(
        "/api/v1/ai/providers/codex/validate",
        json={"api_key": "", "model": "gpt-5.3-codex"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["provider"] == "codex"
    assert payload["model"] == "gpt-5.3-codex"
    assert payload["valid"] is True

    assert len(service.validate_calls) == 1
    call = service.validate_calls[0]
    assert call["provider"] == "codex"
    assert call["api_key"] == ""
    assert call["api_key_provided"] is True
    assert call["model"] == "gpt-5.3-codex"
