import pytest

from app.application.ai_providers.service import (
    AiProviderService,
    CODEX_DISCOVERED_MODELS_KEY,
    CODEX_LAST_SUCCESS_MODEL_KEY,
)
from app.domain.ai_providers.models import ProviderConfig


class MemoryProviderRepo:
    def __init__(self) -> None:
        self._configs: dict[str, ProviderConfig] = {}

    async def list_configs(self):
        return list(self._configs.values())

    async def get_config(self, provider: str):
        return self._configs.get(provider)

    async def upsert(self, config: ProviderConfig):
        self._configs[config.provider] = config
        return config

    async def delete(self, provider: str):
        self._configs.pop(provider, None)


@pytest.mark.asyncio
async def test_list_providers_includes_codex_default():
    service = AiProviderService(MemoryProviderRepo())
    providers = await service.list_providers()
    codex = next((item for item in providers if item.name == "codex"), None)
    assert codex is not None
    assert codex.settings["protocol"] == "codex_cli"
    assert codex.configured is True
    assert "gpt-5.3-codex" in codex.models


@pytest.mark.asyncio
async def test_validate_codex_without_api_key_persists_discovery(monkeypatch):
    repo = MemoryProviderRepo()
    service = AiProviderService(repo)

    async def fake_validate_codex_cli(cli_path: str, timeout_seconds: int, model: str):
        assert cli_path == "codex"
        assert timeout_seconds == 180
        assert model == "gpt-5.3-codex"

    monkeypatch.setattr(
        "app.application.ai_providers.service._validate_codex_cli",
        fake_validate_codex_cli,
    )

    result = await service.validate_provider(
        provider="codex",
        api_key=None,
        api_key_provided=False,
        model="gpt-5.3-codex",
    )

    assert result.valid is True
    saved = await repo.get_config("codex")
    assert saved is not None
    assert saved.settings[CODEX_LAST_SUCCESS_MODEL_KEY] == "gpt-5.3-codex"
    assert "gpt-5.3-codex" in saved.settings[CODEX_DISCOVERED_MODELS_KEY]


@pytest.mark.asyncio
async def test_list_models_uses_hybrid_codex_discovery():
    repo = MemoryProviderRepo()
    await repo.upsert(
        ProviderConfig(
            provider="codex",
            api_key=None,
            default_model="custom-codex-model",
            is_enabled=True,
            settings={
                CODEX_LAST_SUCCESS_MODEL_KEY: "runtime-model",
                CODEX_DISCOVERED_MODELS_KEY: ["runtime-model", "alt-model"],
                "protocol": "codex_cli",
            },
        )
    )
    service = AiProviderService(repo)

    models = await service.list_models("codex")

    assert models[0] == "custom-codex-model"
    assert "runtime-model" in models
    assert "alt-model" in models
    assert "gpt-5.3-codex" in models
