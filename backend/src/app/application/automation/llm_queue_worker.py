from __future__ import annotations

import asyncio
from dataclasses import replace
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.application.ai_providers.service import (
    CODEX_LAST_SUCCESS_MODEL_KEY,
    DEFAULT_PROVIDERS,
    merge_codex_discovered_models,
)
from app.application.automation.config_service import (
    AutomationConfigService,
    DEFAULT_CODEX_REASONING_EFFORT,
)
from app.application.automation.order_queue_service import OrderQueueService
from app.application.automation.llm_queue_service import LlmQueuePolicy
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

logger = logging.getLogger(__name__)

_REVERSE_ACTION_MAP = {
    "OPEN_LONG": "OPEN_SHORT",
    "OPEN_SHORT": "OPEN_LONG",
    "OPEN_LONG_LIMIT": "OPEN_SHORT_LIMIT",
    "OPEN_SHORT_LIMIT": "OPEN_LONG_LIMIT",
}


class LlmQueueWorker:
    def __init__(
        self,
        repository: LlmQueueRepository,
        llm_pipeline: LlmExecutionService,
        order_queue: OrderQueueService,
        outbox: OutboxService,
        provider_repository: ProviderConfigRepository | None = None,
        automation_config_service: AutomationConfigService | None = None,
        policy: Optional[LlmQueuePolicy] = None,
        telegram_notifier: TelegramNotificationService | None = None,
    ) -> None:
        settings = get_settings()
        self._repository = repository
        self._llm_pipeline = llm_pipeline
        self._order_queue = order_queue
        self._outbox = outbox
        self._provider_repository = provider_repository
        self._automation_config_service = automation_config_service
        self._policy = policy or LlmQueuePolicy()
        self._telegram_notifier = telegram_notifier
        self._codex_temp_images = CodexTempImageStore(settings.codex_temp_image_path)
        self._codex_temp_ttl_minutes = max(1, int(settings.codex_temp_image_ttl_minutes))
        self._codex_sweep_interval_seconds = max(1, int(settings.codex_temp_image_sweep_interval_seconds))
        self._last_codex_sweep_at: datetime | None = None
        logger.debug(
            "Codex temp image store configured: base=%s managed_roots=%s ttl_minutes=%s sweep_interval_seconds=%s",
            self._codex_temp_images.base_path,
            [str(path) for path in self._codex_temp_images.managed_roots],
            self._codex_temp_ttl_minutes,
            self._codex_sweep_interval_seconds,
        )

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
        reasoning_effort = await self._resolve_reasoning_effort(
            payload.get("reasoning_effort"),
            provider=payload.get("provider"),
            model=payload.get("model"),
        )

        request = LlmCallRequest(
            prompt_text=prompt_text,
            images=extract_chart_images(data),
            model=payload.get("model") or settings.llm_model,
            temperature=temperature,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
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

        reverse_order_enabled = await self._resolve_reverse_order_enabled()
        transformed_ideas, order_reversal_metadata, reversed_actions = _apply_reverse_order_transform(
            result.parse_result.ideas,
            reverse_order_enabled,
        )
        reverse_order_applied = len(reversed_actions) > 0
        execution_ideas = [idea.to_dict() for idea in transformed_ideas]
        result_payload["parse_result"]["ideas"] = execution_ideas

        await self._repository.mark_done(item.id, result_payload)
        self._delete_codex_images_from_response(result.call_response.raw_response)

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
                    "parse_result": result_payload["parse_result"],
                    "execution_ideas": execution_ideas,
                    "protocol": protocol,
                    "response_meta": response_meta,
                    "reverse_order_enabled": reverse_order_enabled,
                    "reverse_order_applied": reverse_order_applied,
                    "reversed_actions": reversed_actions,
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
                    "parse_result": result_payload["parse_result"],
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

        for idea, reversal_meta in zip(execution_ideas, order_reversal_metadata):
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
                        "reverse_order_applied": reversal_meta["reverse_order_applied"],
                        "original_action": reversal_meta["original_action"],
                        "effective_action": reversal_meta["effective_action"],
                        "cycle_number": cycle_number,
                    },
                    session_id,
                ),
            )

        return True

    async def _resolve_reasoning_effort(
        self,
        value: object,
        *,
        provider: object,
        model: object,
    ) -> Optional[str]:
        normalized = _normalize_reasoning_effort_value(value)
        resolved_provider = _normalize_provider(provider)
        resolved_model = str(model or "").strip()
        if normalized:
            return normalized
        if resolved_provider != "codex" and _infer_protocol_from_model(resolved_model) != "codex_cli":
            return None
        if self._automation_config_service is not None:
            try:
                config = await self._automation_config_service.get_config()
            except Exception:
                config = None
            if config is not None:
                normalized = _normalize_reasoning_effort_value(config.reasoning_effort)
                if normalized:
                    return normalized
        return DEFAULT_CODEX_REASONING_EFFORT

    async def _maybe_sweep_codex_images(self) -> None:
        now = datetime.now(timezone.utc)
        if self._last_codex_sweep_at is not None:
            elapsed = (now - self._last_codex_sweep_at).total_seconds()
            if elapsed < self._codex_sweep_interval_seconds:
                return
        deleted = self._codex_temp_images.sweep_expired(self._codex_temp_ttl_minutes)
        self._last_codex_sweep_at = now
        if deleted > 0:
            logger.info(
                "Codex temp image sweep removed %s file(s); managed_roots=%s",
                deleted,
                [str(path) for path in self._codex_temp_images.managed_roots],
            )

    def _delete_codex_images_from_response(self, raw_response: Optional[dict]) -> None:
        if not isinstance(raw_response, dict):
            return
        if str(raw_response.get("protocol")).lower() != "codex_cli":
            return
        image_paths = raw_response.get("image_paths")
        if not isinstance(image_paths, list):
            return
        deleted = self._codex_temp_images.delete_paths([str(path) for path in image_paths if path])
        if deleted > 0:
            logger.info(
                "Codex temp image immediate cleanup removed %s file(s)",
                deleted,
            )

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

    async def _resolve_reverse_order_enabled(self) -> bool:
        if self._automation_config_service is None:
            return False
        try:
            config = await self._automation_config_service.get_config()
        except Exception:
            return False
        return bool(getattr(config, "reverse_order_enabled", False))


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


def _normalize_reasoning_effort_value(value: object) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in {"minimal", "low", "medium", "high", "xhigh"}:
        return normalized
    return None


def _apply_reverse_order_transform(ideas, reverse_order_enabled: bool):
    transformed_ideas = []
    order_metadata = []
    reversed_actions = []

    for idea in ideas:
        original_action = idea.action.value
        effective_action = original_action
        reverse_order_applied = False
        transformed_idea = idea

        if reverse_order_enabled:
            reversed_action = _REVERSE_ACTION_MAP.get(original_action)
            if reversed_action:
                transformed_idea = replace(idea, action=idea.action.__class__(reversed_action))
                effective_action = reversed_action
                reverse_order_applied = True
                reversed_actions.append(
                    {
                        "symbol": idea.symbol,
                        "original_action": original_action,
                        "effective_action": effective_action,
                    }
                )

        transformed_ideas.append(transformed_idea)
        order_metadata.append(
            {
                "symbol": idea.symbol,
                "original_action": original_action,
                "effective_action": effective_action,
                "reverse_order_applied": reverse_order_applied,
            }
        )

    return transformed_ideas, order_metadata, reversed_actions


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
