from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.application.ai_providers.service import (
    CODEX_LAST_SUCCESS_MODEL_KEY,
    DEFAULT_PROVIDERS,
    merge_codex_discovered_models,
)
from app.application.automation.llm_queue_service import LlmQueuePolicy
from app.application.automation.order_queue_service import OrderQueueService
from app.application.automation import topics
from app.application.bus.outbox_service import OutboxService
from app.application.llm_caller.service import extract_chart_images
from app.application.llm_pipeline.service import LlmExecutionService
from app.application.automation.execution_mode import (
    normalize_execution_mode,
    should_enqueue_orders,
)
from app.application.telegram.notifications_service import TelegramNotificationService
from app.domain.ai_providers.models import ProviderConfig
from app.domain.llm_caller.models import LlmCallRequest
from app.domain.ai_providers.interfaces import ProviderConfigRepository
from app.infrastructure.external.codex_temp_images import CodexTempImageStore
from app.infrastructure.repositories.llm_queue_repository import LlmQueueRepository, LlmQueueItem
from app.settings import get_settings


class LlmQueueWorker:
    def __init__(
        self,
        repository: LlmQueueRepository,
        llm_pipeline: LlmExecutionService,
        order_queue: OrderQueueService,
        outbox: OutboxService,
        provider_repository: ProviderConfigRepository | None = None,
        policy: Optional[LlmQueuePolicy] = None,
        telegram_notifier: TelegramNotificationService | None = None,
    ) -> None:
        settings = get_settings()
        self._repository = repository
        self._llm_pipeline = llm_pipeline
        self._order_queue = order_queue
        self._outbox = outbox
        self._provider_repository = provider_repository
        self._policy = policy or LlmQueuePolicy()
        self._telegram_notifier = telegram_notifier
        self._codex_temp_images = CodexTempImageStore(settings.codex_temp_image_path)
        self._codex_temp_ttl_minutes = max(1, int(settings.codex_temp_image_ttl_minutes))
        self._codex_sweep_interval_seconds = max(1, int(settings.codex_temp_image_sweep_interval_seconds))
        self._last_codex_sweep_at: datetime | None = None

    async def process_next(self) -> bool:
        await self._maybe_sweep_codex_images()

        item = await self._repository.claim_next()
        if item is None:
            return False

        payload = item.payload
        session_id = payload.get("session_id")
        cycle_number = payload.get("cycle_number")

        if _is_expired(item, self._policy):
            await self._repository.mark_dropped(item.id, "expired")
            await self._outbox.enqueue_event(
                topics.LLM_FAILED,
                _with_session(
                    {"request_id": item.id, "error": "expired", "cycle_number": cycle_number},
                    session_id,
                ),
            )
            return True

        prompt_text = payload.get("prompt_text")
        data = payload.get("data") or {}
        if not prompt_text:
            await self._repository.mark_failed(item.id, "missing prompt_text")
            await self._outbox.enqueue_event(
                topics.LLM_FAILED,
                _with_session(
                    {"request_id": item.id, "error": "missing prompt_text", "cycle_number": cycle_number},
                    session_id,
                ),
            )
            return True

        execution_mode = normalize_execution_mode(payload.get("execution_mode"))
        settings = get_settings()
        temperature = payload.get("temperature")
        if temperature is None:
            temperature = settings.llm_temperature
        max_tokens = payload.get("max_tokens")
        if max_tokens is None:
            max_tokens = settings.llm_max_tokens

        request = LlmCallRequest(
            prompt_text=prompt_text,
            images=extract_chart_images(data),
            model=payload.get("model") or settings.llm_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        resolved_provider = _normalize_provider(payload.get("provider"))
        api_key, base_url, protocol = await _resolve_provider_overrides(
            self._provider_repository,
            resolved_provider,
        )
        if not protocol:
            protocol = _infer_protocol_from_model(request.model)
        if not resolved_provider and protocol == "codex_cli":
            resolved_provider = "codex"

        await self._outbox.enqueue_event(
            topics.LLM_REQUESTED,
            _with_session(
                {
                    "request_id": payload.get("request_id", item.id),
                    "provider": resolved_provider,
                    "protocol": protocol,
                    "model": request.model,
                    "prompt_chars": len(prompt_text),
                    "execution_mode": execution_mode.value,
                    "cycle_number": cycle_number,
                },
                session_id,
            ),
        )

        try:
            result = await self._llm_pipeline.execute(
                request,
                api_key=api_key,
                base_url=base_url,
                protocol=protocol,
                provider=resolved_provider,
            )
        except Exception as exc:
            error_text = str(exc).strip() or f"{exc.__class__.__name__}"
            await self._repository.mark_failed(item.id, error_text)
            await self._outbox.enqueue_event(
                topics.LLM_FAILED,
                _with_session(
                    {
                        "request_id": payload.get("request_id", item.id),
                        "error": error_text,
                        "provider": resolved_provider,
                        "model": request.model,
                        "protocol": protocol,
                        "cycle_number": cycle_number,
                    },
                    session_id,
                ),
            )
            return True

        if protocol == "codex_cli":
            await self._persist_codex_provider_discovery(
                provider=resolved_provider,
                model=result.call_response.model,
            )

        result_payload = result.to_dict()

        if not result.parse_result.success:
            await self._repository.mark_failed(item.id, result.parse_result.error or "parse_failed")
            await self._outbox.enqueue_event(
                topics.PARSER_FAILED,
                _with_session(
                    {
                        "request_id": payload.get("request_id", item.id),
                        "error": result.parse_result.error,
                        "parse_result": result.parse_result.to_dict(),
                        "llm_response": result.call_response.content,
                        "protocol": protocol,
                        "cycle_number": cycle_number,
                        "response_meta": {
                            "model": result.call_response.model,
                            "tokens_used": result.call_response.tokens_used,
                            "latency_ms": result.call_response.latency_ms,
                        },
                    },
                    session_id,
                ),
            )
            await self._outbox.enqueue_event(
                topics.LLM_FAILED,
                _with_session(
                    {
                        "request_id": payload.get("request_id", item.id),
                        "error": result.parse_result.error,
                        "raw_response": result.call_response.content,
                        "llm_response": result.call_response.content,
                        "protocol": protocol,
                        "cycle_number": cycle_number,
                        "response_meta": {
                            "model": result.call_response.model,
                            "tokens_used": result.call_response.tokens_used,
                            "latency_ms": result.call_response.latency_ms,
                        },
                    },
                    session_id,
                ),
            )
            return True

        await self._repository.mark_done(item.id, result_payload)
        self._delete_codex_images_from_response(result.call_response.raw_response)

        execution_ideas = [idea.to_dict() for idea in result.parse_result.ideas]
        response_meta = {
            "model": result.call_response.model,
            "tokens_used": result.call_response.tokens_used,
            "latency_ms": result.call_response.latency_ms,
        }
        await self._outbox.enqueue_event(
            topics.PARSER_COMPLETED,
            _with_session(
                {
                    "request_id": payload.get("request_id", item.id),
                    "parse_result": result.parse_result.to_dict(),
                    "execution_ideas": execution_ideas,
                    "protocol": protocol,
                    "response_meta": response_meta,
                    "cycle_number": cycle_number,
                },
                session_id,
            ),
        )
        await self._outbox.enqueue_event(
            topics.LLM_COMPLETED,
            _with_session(
                {
                    "request_id": payload.get("request_id", item.id),
                    "execution_ideas": execution_ideas,
                    "considerations": result.parse_result.considerations,
                    "execution_mode": execution_mode.value,
                    "llm_response": result.call_response.content,
                    "protocol": protocol,
                    "response_meta": response_meta,
                    "parse_result": result.parse_result.to_dict(),
                    "cycle_number": cycle_number,
                },
                session_id,
            ),
        )

        if self._telegram_notifier and result.parse_result.considerations:
            asyncio.create_task(
                self._telegram_notifier.notify_llm_considerations(
                    result.parse_result.considerations,
                    cycle_number=payload.get("cycle_number"),
                    session_id=session_id,
                )
            )

        if not should_enqueue_orders(execution_mode):
            return True

        for idea in execution_ideas:
            await self._order_queue.enqueue(
                {
                    "source_request_id": payload.get("request_id", item.id),
                    "session_id": session_id,
                    "trace_id": payload.get("trace_id"),
                    "execution_idea": idea,
                    "execution_mode": execution_mode.value,
                    "cycle_number": cycle_number,
                }
            )
            await self._outbox.enqueue_event(
                topics.ORDER_QUEUED,
                _with_session(
                    {
                        "execution_idea": idea,
                        "execution_mode": execution_mode.value,
                        "cycle_number": cycle_number,
                    },
                    session_id,
                ),
            )

        return True

    async def _maybe_sweep_codex_images(self) -> None:
        now = datetime.now(timezone.utc)
        if self._last_codex_sweep_at is not None:
            elapsed = (now - self._last_codex_sweep_at).total_seconds()
            if elapsed < self._codex_sweep_interval_seconds:
                return
        self._codex_temp_images.sweep_expired(self._codex_temp_ttl_minutes)
        self._last_codex_sweep_at = now

    def _delete_codex_images_from_response(self, raw_response: Optional[dict]) -> None:
        if not isinstance(raw_response, dict):
            return
        if str(raw_response.get("protocol")).lower() != "codex_cli":
            return
        image_paths = raw_response.get("image_paths")
        if not isinstance(image_paths, list):
            return
        self._codex_temp_images.delete_paths([str(path) for path in image_paths if path])

    async def _persist_codex_provider_discovery(self, provider: Optional[str], model: Optional[str]) -> None:
        if self._provider_repository is None:
            return
        provider_id = _normalize_provider(provider)
        if not provider_id:
            return

        defaults = DEFAULT_PROVIDERS.get(provider_id)
        existing = await self._provider_repository.get_config(provider_id)
        settings = dict(existing.settings or {}) if existing else {}
        merged = merge_codex_discovered_models(
            settings,
            model=model,
            default_model=existing.default_model if existing else None,
            default_models=(defaults.models if defaults else []),
        )

        resolved_default_model = existing.default_model if existing else None
        if not resolved_default_model:
            resolved_default_model = str(merged.get(CODEX_LAST_SUCCESS_MODEL_KEY)).strip() if merged.get(CODEX_LAST_SUCCESS_MODEL_KEY) else None

        config = ProviderConfig(
            provider=provider_id,
            api_key=existing.api_key if existing else None,
            default_model=resolved_default_model,
            is_enabled=existing.is_enabled if existing else True,
            settings=merged or None,
            created_at=existing.created_at if existing else None,
            updated_at=existing.updated_at if existing else None,
        )
        await self._provider_repository.upsert(config)


def _is_expired(item: LlmQueueItem, policy: LlmQueuePolicy) -> bool:
    now = datetime.now(timezone.utc)
    expires_at = item.expires_at
    if expires_at is None:
        expires_at = item.created_at + timedelta(minutes=policy.ttl_minutes)
    return now > expires_at


def _with_session(payload: dict, session_id: Optional[str]) -> dict:
    if session_id:
        payload = dict(payload)
        payload["session_id"] = session_id
    return payload


def _normalize_provider(provider: Optional[str]) -> Optional[str]:
    if not provider:
        return None
    normalized = provider.strip().lower()
    return normalized or None


def _resolve_base_url(provider: str, settings: Optional[dict]) -> Optional[str]:
    if settings and settings.get("base_url"):
        return str(settings["base_url"]).rstrip("/")
    defaults = DEFAULT_PROVIDERS.get(provider)
    if defaults and defaults.base_url:
        return defaults.base_url.rstrip("/")
    return None


def _resolve_protocol(provider: str, settings: Optional[dict]) -> str:
    if settings and settings.get("protocol"):
        return str(settings["protocol"]).lower()
    defaults = DEFAULT_PROVIDERS.get(provider)
    if defaults:
        return defaults.protocol
    return "openai"


def _infer_protocol_from_model(model: Optional[str]) -> Optional[str]:
    if not isinstance(model, str):
        return None
    normalized = model.strip().lower()
    if not normalized:
        return None
    if "codex" in normalized:
        return "codex_cli"
    return None


async def _resolve_provider_config(
    repository: ProviderConfigRepository | None,
    provider: Optional[str],
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    normalized = _normalize_provider(provider)
    if not normalized:
        return None, None, None
    config = await repository.get_config(normalized) if repository else None
    api_key = config.api_key if config else None
    settings = config.settings if config else None
    base_url = _resolve_base_url(normalized, settings)
    protocol = _resolve_protocol(normalized, settings)
    return api_key, base_url, protocol


async def _resolve_provider_overrides(
    repository: ProviderConfigRepository | None,
    provider: Optional[str],
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    return await _resolve_provider_config(repository, provider)
