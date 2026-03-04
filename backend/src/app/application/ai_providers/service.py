from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from app.domain.ai_providers.interfaces import ProviderConfigRepository
from app.domain.ai_providers.models import ProviderConfig, ProviderInfo, ProviderValidationResult
from app.infrastructure.external.codex_cli import CodexCliError, execute_codex_cli


CODEX_LAST_SUCCESS_MODEL_KEY = "codex_last_success_model"
CODEX_DISCOVERED_MODELS_KEY = "codex_discovered_models"
CODEX_DISCOVERED_MODELS_MAX = 20
CODEX_FALLBACK_MODELS = [
    "gpt-5.3-codex",
    "gpt-5-codex",
    "gpt-5.1-codex",
]


@dataclass(frozen=True)
class ProviderDefaults:
    name: str
    display_name: str
    protocol: str
    models: List[str]
    base_url: Optional[str] = None


DEFAULT_PROVIDERS: Dict[str, ProviderDefaults] = {
    "openai": ProviderDefaults(
        name="openai",
        display_name="OpenAI",
        protocol="openai",
        models=["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
        base_url="https://api.openai.com/v1",
    ),
    "gemini": ProviderDefaults(
        name="gemini",
        display_name="Gemini",
        protocol="gemini",
        models=["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
    ),
    "claude": ProviderDefaults(
        name="claude",
        display_name="Claude",
        protocol="claude",
        models=["claude-sonnet-4-20250514", "claude-3-5-sonnet-20241022", "claude-3-haiku-20240307"],
    ),
    "xai": ProviderDefaults(
        name="xai",
        display_name="xAI",
        protocol="openai",
        models=["grok-4-latest", "grok-3-latest", "grok-3-fast-latest", "grok-beta"],
        base_url="https://api.x.ai/v1",
    ),
    "deepseek": ProviderDefaults(
        name="deepseek",
        display_name="DeepSeek",
        protocol="openai",
        models=["deepseek-chat", "deepseek-reasoner"],
        base_url="https://api.deepseek.com",
    ),
    "codex": ProviderDefaults(
        name="codex",
        display_name="Codex CLI",
        protocol="codex_cli",
        models=CODEX_FALLBACK_MODELS,
    ),
}


class AiProviderService:
    def __init__(
        self,
        repository: ProviderConfigRepository,
        codex_cli_path: str = "codex",
        codex_cli_timeout_seconds: int = 180,
    ) -> None:
        self._repository = repository
        self._codex_cli_path = codex_cli_path
        self._codex_cli_timeout_seconds = codex_cli_timeout_seconds

    async def list_providers(self) -> List[ProviderInfo]:
        configs = await self._repository.list_configs()
        config_map = {config.provider: config for config in configs}
        providers: List[ProviderInfo] = []

        for name, defaults in DEFAULT_PROVIDERS.items():
            config = config_map.pop(name, None)
            providers.append(self._build_info(defaults, config))

        for provider in sorted(config_map.keys()):
            config = config_map[provider]
            providers.append(self._build_info(None, config))

        return providers

    async def upsert_provider(
        self,
        provider: str,
        api_key: Optional[str],
        api_key_provided: bool,
        default_model: Optional[str],
        default_model_provided: bool,
        is_enabled: Optional[bool],
        is_enabled_provided: bool,
        base_url: Optional[str],
        base_url_provided: bool,
        display_name: Optional[str],
        display_name_provided: bool,
        protocol: Optional[str],
        protocol_provided: bool,
    ) -> ProviderInfo:
        provider_id = _normalize_provider(provider)
        if not provider_id:
            raise ValueError("provider is required")

        defaults = DEFAULT_PROVIDERS.get(provider_id)
        existing = await self._repository.get_config(provider_id)

        settings = dict(existing.settings or {}) if existing else {}

        if not defaults and not base_url_provided and not settings.get("base_url"):
            raise ValueError("base_url is required for custom providers")

        if base_url_provided:
            if base_url:
                settings["base_url"] = base_url.strip().rstrip("/")
            else:
                settings.pop("base_url", None)

        if display_name_provided:
            if display_name:
                settings["display_name"] = display_name.strip()
            else:
                settings.pop("display_name", None)

        if protocol_provided:
            if protocol:
                settings["protocol"] = protocol.strip().lower()
            else:
                settings.pop("protocol", None)

        resolved_key = existing.api_key if existing and not api_key_provided else _normalize_key(api_key)
        resolved_default = existing.default_model if existing and not default_model_provided else default_model
        resolved_enabled = existing.is_enabled if existing and not is_enabled_provided else bool(is_enabled)

        config = ProviderConfig(
            provider=provider_id,
            api_key=resolved_key,
            default_model=resolved_default,
            is_enabled=resolved_enabled,
            settings=settings or None,
            created_at=existing.created_at if existing else None,
            updated_at=existing.updated_at if existing else None,
        )
        saved = await self._repository.upsert(config)
        return self._build_info(defaults, saved)

    async def delete_provider(self, provider: str) -> None:
        provider_id = _normalize_provider(provider)
        if not provider_id:
            raise ValueError("provider is required")
        await self._repository.delete(provider_id)

    async def list_models(self, provider: str) -> List[str]:
        provider_id = _normalize_provider(provider)
        if not provider_id:
            raise ValueError("provider is required")

        defaults = DEFAULT_PROVIDERS.get(provider_id)
        config = await self._repository.get_config(provider_id)

        protocol = _resolve_protocol(defaults, config)
        base_url = _resolve_base_url(defaults, config)
        api_key = config.api_key if config else None
        default_models = defaults.models if defaults else []

        if protocol == "codex_cli":
            return _list_codex_models(defaults, config)

        if protocol == "openai" and base_url:
            fetched = await _fetch_openai_models(base_url, api_key)
            if fetched:
                return _dedupe(fetched)

        return _dedupe(default_models)

    async def validate_provider(
        self,
        provider: str,
        api_key: Optional[str],
        api_key_provided: bool,
        model: Optional[str],
    ) -> ProviderValidationResult:
        provider_id = _normalize_provider(provider)
        if not provider_id:
            raise ValueError("provider is required")

        defaults = DEFAULT_PROVIDERS.get(provider_id)
        config = await self._repository.get_config(provider_id)

        protocol = _resolve_protocol(defaults, config)
        base_url = _resolve_base_url(defaults, config)
        resolved_key = config.api_key if config and not api_key_provided else _normalize_key(api_key)
        resolved_model = model or (config.default_model if config else None)
        if not resolved_model:
            codex_models = _list_codex_models(defaults, config) if protocol == "codex_cli" else []
            if codex_models:
                resolved_model = codex_models[0]
        if not resolved_model and defaults and defaults.models:
            resolved_model = defaults.models[0]
        if not resolved_model:
            raise ValueError("model is required for validation")

        start = time.time()
        if protocol == "openai":
            if not resolved_key:
                raise ValueError("API key is required for validation")
            if not base_url:
                raise ValueError("base_url is required for OpenAI-compatible providers")
            await _validate_openai(base_url, resolved_key, resolved_model)
        elif protocol == "gemini":
            if not resolved_key:
                raise ValueError("API key is required for validation")
            await _validate_gemini(resolved_key, resolved_model)
        elif protocol == "claude":
            if not resolved_key:
                raise ValueError("API key is required for validation")
            await _validate_claude(resolved_key, resolved_model)
        elif protocol == "codex_cli":
            await _validate_codex_cli(
                cli_path=self._codex_cli_path,
                timeout_seconds=self._codex_cli_timeout_seconds,
                model=resolved_model,
            )
            await self._persist_codex_discovery(
                provider=provider_id,
                model=resolved_model,
                defaults=defaults,
                existing=config,
            )
        else:
            raise ValueError(f"unsupported protocol: {protocol}")

        latency_ms = (time.time() - start) * 1000.0
        return ProviderValidationResult(
            provider=provider_id,
            model=resolved_model,
            latency_ms=latency_ms,
            valid=True,
        )

    def _build_info(self, defaults: Optional[ProviderDefaults], config: Optional[ProviderConfig]) -> ProviderInfo:
        settings = {}
        if defaults:
            settings["display_name"] = defaults.display_name
            settings["protocol"] = defaults.protocol
            if defaults.base_url:
                settings["base_url"] = defaults.base_url

        if config and config.settings:
            settings.update(config.settings)

        name = defaults.name if defaults else (config.provider if config else "")
        protocol = _resolve_protocol(defaults, config)
        models = _list_codex_models(defaults, config) if protocol == "codex_cli" else (defaults.models if defaults else [])
        configured = _is_provider_configured(protocol, config)
        is_enabled = config.is_enabled if config else True
        default_model = config.default_model if config else None

        if not settings:
            settings = None

        return ProviderInfo(
            name=name,
            models=models,
            configured=configured,
            is_enabled=is_enabled,
            default_model=default_model,
            settings=settings,
        )

    async def _persist_codex_discovery(
        self,
        *,
        provider: str,
        model: Optional[str],
        defaults: Optional[ProviderDefaults],
        existing: Optional[ProviderConfig],
    ) -> None:
        if not provider:
            return

        current_settings = dict(existing.settings or {}) if existing else {}
        merged_settings = merge_codex_discovered_models(
            current_settings,
            model=model,
            default_model=existing.default_model if existing else None,
            default_models=(defaults.models if defaults else []),
        )
        resolved_default_model = existing.default_model if existing else None
        if not resolved_default_model:
            resolved_default_model = model or None
        config = ProviderConfig(
            provider=provider,
            api_key=existing.api_key if existing else None,
            default_model=resolved_default_model,
            is_enabled=existing.is_enabled if existing else True,
            settings=merged_settings or None,
            created_at=existing.created_at if existing else None,
            updated_at=existing.updated_at if existing else None,
        )
        await self._repository.upsert(config)


def _normalize_provider(provider: str) -> str:
    return provider.strip().lower() if provider else ""


def _normalize_key(api_key: Optional[str]) -> Optional[str]:
    if api_key is None:
        return None
    trimmed = api_key.strip()
    return trimmed if trimmed else None


def _resolve_protocol(defaults: Optional[ProviderDefaults], config: Optional[ProviderConfig]) -> str:
    if config and config.settings and config.settings.get("protocol"):
        return str(config.settings["protocol"]).lower()
    if defaults:
        return defaults.protocol
    return "openai"


def _resolve_base_url(defaults: Optional[ProviderDefaults], config: Optional[ProviderConfig]) -> Optional[str]:
    if config and config.settings and config.settings.get("base_url"):
        return str(config.settings["base_url"]).rstrip("/")
    if defaults and defaults.base_url:
        return defaults.base_url.rstrip("/")
    return None


def _is_provider_configured(protocol: str, config: Optional[ProviderConfig]) -> bool:
    if protocol == "codex_cli":
        return True
    return bool(config and config.api_key)


def _list_codex_models(defaults: Optional[ProviderDefaults], config: Optional[ProviderConfig]) -> List[str]:
    settings = config.settings if config else None
    discovered = _as_model_list(settings.get(CODEX_DISCOVERED_MODELS_KEY) if settings else None)
    last_success = str(settings.get(CODEX_LAST_SUCCESS_MODEL_KEY)).strip() if settings and settings.get(CODEX_LAST_SUCCESS_MODEL_KEY) else None

    candidates: List[str] = []
    if config and config.default_model:
        candidates.append(config.default_model)
    if last_success:
        candidates.append(last_success)
    candidates.extend(discovered)
    if defaults:
        candidates.extend(defaults.models)
    if not candidates:
        candidates.extend(CODEX_FALLBACK_MODELS)
    return _dedupe(candidates)


def merge_codex_discovered_models(
    settings: Optional[dict],
    *,
    model: Optional[str],
    default_model: Optional[str],
    default_models: Sequence[str],
) -> dict:
    merged = dict(settings or {})
    discovered = _as_model_list(merged.get(CODEX_DISCOVERED_MODELS_KEY))
    last_success = merged.get(CODEX_LAST_SUCCESS_MODEL_KEY)

    candidates: List[str] = []
    if model:
        candidates.append(str(model).strip())
    if default_model:
        candidates.append(str(default_model).strip())
    if last_success:
        candidates.append(str(last_success).strip())
    candidates.extend(discovered)
    candidates.extend([str(item).strip() for item in default_models if str(item).strip()])

    deduped = _dedupe([item for item in candidates if item])
    if deduped:
        merged[CODEX_DISCOVERED_MODELS_KEY] = deduped[:CODEX_DISCOVERED_MODELS_MAX]
    else:
        merged.pop(CODEX_DISCOVERED_MODELS_KEY, None)

    if model and str(model).strip():
        merged[CODEX_LAST_SUCCESS_MODEL_KEY] = str(model).strip()

    return merged


def _as_model_list(value: object) -> List[str]:
    if not isinstance(value, list):
        return []
    models: List[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if cleaned:
            models.append(cleaned)
    return models


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        if not item:
            continue
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


async def _fetch_openai_models(base_url: str, api_key: Optional[str]) -> List[str]:
    try:
        import httpx
    except Exception:
        return []

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    url = f"{base_url.rstrip('/')}/models"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return []

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return []
    models = [str(item.get("id")) for item in data if isinstance(item, dict) and item.get("id")]
    return _dedupe(models)


async def _validate_openai(base_url: str, api_key: str, model: str) -> None:
    try:
        import httpx
    except Exception as exc:
        raise RuntimeError("httpx is required for LLM validation") from exc

    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": 'Say "OK" to confirm connectivity.'}],
        "temperature": 0.0,
        "max_tokens": 10,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()


async def _validate_gemini(api_key: str, model: str) -> None:
    try:
        import httpx
    except Exception as exc:
        raise RuntimeError("httpx is required for LLM validation") from exc

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {"contents": [{"parts": [{"text": 'Say "OK" to confirm connectivity.'}]}]}
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, params={"key": api_key}, json=payload)
        response.raise_for_status()


async def _validate_claude(api_key: str, model: str) -> None:
    try:
        import httpx
    except Exception as exc:
        raise RuntimeError("httpx is required for LLM validation") from exc

    payload = {
        "model": model,
        "max_tokens": 16,
        "messages": [{"role": "user", "content": 'Say "OK" to confirm connectivity.'}],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
        response.raise_for_status()


async def _validate_codex_cli(cli_path: str, timeout_seconds: int, model: str) -> None:
    try:
        await execute_codex_cli(
            prompt_text='Reply with exactly "OK".',
            model=model,
            images=[],
            cli_path=cli_path,
            timeout_seconds=timeout_seconds,
        )
    except CodexCliError as exc:
        raise ValueError(str(exc)) from exc
