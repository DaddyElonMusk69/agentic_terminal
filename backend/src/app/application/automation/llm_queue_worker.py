from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.application.automation.llm_queue_service import LlmQueuePolicy
from app.application.automation.order_queue_service import OrderQueueService
from app.application.automation import topics
from app.application.bus.outbox_service import OutboxService
from app.application.llm_caller.service import extract_chart_images
from app.application.llm_pipeline.service import LlmExecutionService
from app.application.automation.execution_mode import (
    normalize_execution_mode,
    should_enqueue_orders,
    should_execute_trades,
)
from app.application.telegram.notifications_service import TelegramNotificationService
from app.domain.llm_caller.models import LlmCallRequest
from app.domain.ai_providers.interfaces import ProviderConfigRepository
from app.infrastructure.repositories.llm_queue_repository import LlmQueueRepository, LlmQueueItem
from app.application.ai_providers.service import DEFAULT_PROVIDERS
from app.settings import get_settings


class LlmQueueWorker:
    def __init__(
        self,
        repository: LlmQueueRepository,
        llm_pipeline: LlmExecutionService,
        order_queue: OrderQueueService,
        outbox: OutboxService,
        provider_repository: ProviderConfigRepository,
        policy: Optional[LlmQueuePolicy] = None,
        telegram_notifier: TelegramNotificationService | None = None,
    ) -> None:
        self._repository = repository
        self._llm_pipeline = llm_pipeline
        self._order_queue = order_queue
        self._outbox = outbox
        self._provider_repository = provider_repository
        self._policy = policy or LlmQueuePolicy()
        self._telegram_notifier = telegram_notifier

    async def process_next(self) -> bool:
        item = await self._repository.claim_next()
        if item is None:
            return False

        payload = item.payload
        session_id = payload.get("session_id")

        if _is_expired(item, self._policy):
            await self._repository.mark_dropped(item.id, "expired")
            await self._outbox.enqueue_event(
                topics.LLM_FAILED,
                _with_session({"request_id": item.id, "error": "expired"}, session_id),
            )
            return True

        prompt_text = payload.get("prompt_text")
        data = payload.get("data") or {}
        if not prompt_text:
            await self._repository.mark_failed(item.id, "missing prompt_text")
            await self._outbox.enqueue_event(
                topics.LLM_FAILED,
                _with_session({"request_id": item.id, "error": "missing prompt_text"}, session_id),
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

        await self._outbox.enqueue_event(
            topics.LLM_REQUESTED,
            _with_session(
                {
                    "request_id": payload.get("request_id", item.id),
                    "provider": payload.get("provider") or None,
                    "model": request.model,
                    "prompt_chars": len(prompt_text),
                    "execution_mode": execution_mode.value,
                },
                session_id,
            ),
        )

        api_key, base_url, protocol = await _resolve_provider_overrides(
            self._provider_repository,
            payload.get("provider"),
        )
        if protocol and protocol != "openai":
            await self._repository.mark_failed(item.id, f"unsupported_protocol:{protocol}")
            await self._outbox.enqueue_event(
                topics.LLM_FAILED,
                _with_session(
                    {
                        "request_id": payload.get("request_id", item.id),
                        "error": f"unsupported_protocol:{protocol}",
                    },
                    session_id,
                ),
            )
            return True

        try:
            result = await self._llm_pipeline.execute(
                request,
                api_key=api_key,
                base_url=base_url,
            )
        except Exception as exc:
            await self._repository.mark_failed(item.id, str(exc))
            await self._outbox.enqueue_event(
                topics.LLM_FAILED,
                _with_session(
                    {
                        "request_id": payload.get("request_id", item.id),
                        "error": str(exc),
                    },
                    session_id,
                ),
            )
            return True

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
                    "response_meta": response_meta,
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
                    "response_meta": response_meta,
                    "parse_result": result.parse_result.to_dict(),
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
                }
            )
            await self._outbox.enqueue_event(
                topics.ORDER_QUEUED,
                _with_session(
                    {"execution_idea": idea, "execution_mode": execution_mode.value},
                    session_id,
                ),
            )

        return True


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


async def _resolve_provider_config(
    repository: ProviderConfigRepository,
    provider: Optional[str],
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    normalized = _normalize_provider(provider)
    if not normalized:
        return None, None, None
    config = await repository.get_config(normalized)
    if not config:
        return None, None, None
    api_key = config.api_key
    base_url = _resolve_base_url(normalized, config.settings)
    protocol = _resolve_protocol(normalized, config.settings)
    return api_key, base_url, protocol


async def _resolve_provider_overrides(
    repository: ProviderConfigRepository,
    provider: Optional[str],
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    return await _resolve_provider_config(repository, provider)
