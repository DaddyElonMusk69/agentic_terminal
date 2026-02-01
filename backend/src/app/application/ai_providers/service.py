from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from app.domain.ai_providers.interfaces import ProviderConfigRepository
from app.domain.ai_providers.models import ProviderConfig, ProviderInfo, ProviderValidationResult


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
}


class AiProviderService:
    def __init__(self, repository: ProviderConfigRepository) -> None:
        self._repository = repository

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

        resolved_key = config.api_key if config and not api_key_provided else _normalize_key(api_key)
        if not resolved_key:
            raise ValueError("API key is required for validation")

        protocol = _resolve_protocol(defaults, config)
        base_url = _resolve_base_url(defaults, config)
        resolved_model = model or (config.default_model if config else None)
        if not resolved_model and defaults and defaults.models:
            resolved_model = defaults.models[0]
        if not resolved_model:
            raise ValueError("model is required for validation")

        start = time.time()
        if protocol == "openai":
            if not base_url:
                raise ValueError("base_url is required for OpenAI-compatible providers")
            await _validate_openai(base_url, resolved_key, resolved_model)
        elif protocol == "gemini":
            await _validate_gemini(resolved_key, resolved_model)
        elif protocol == "claude":
            await _validate_claude(resolved_key, resolved_model)
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
        models = defaults.models if defaults else []
        configured = bool(config and config.api_key)
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
