from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.application.automation.llm_queue_service import LlmQueueService
from app.application.automation.execution_mode import normalize_execution_mode, should_enqueue_llm
from app.application.automation import topics
from app.application.bus.outbox_service import OutboxService
from app.application.prompt_builder.service import PromptBuilderService, PromptBuildError
from app.domain.prompt_builder.models import PromptBuildRequest
from app.infrastructure.repositories.prompt_build_queue_repository import (
    PromptBuildQueueRepository,
    PromptBuildQueueItem,
)


class PromptPipelineWorker:
    def __init__(
        self,
        repository: PromptBuildQueueRepository,
        prompt_builder: PromptBuilderService,
        llm_queue: LlmQueueService,
        outbox: OutboxService,
        ttl_minutes: int = 20,
        quant_retry_seconds: int = 10,
    ) -> None:
        self._repository = repository
        self._prompt_builder = prompt_builder
        self._llm_queue = llm_queue
        self._outbox = outbox
        self._ttl_minutes = ttl_minutes
        self._quant_retry_seconds = quant_retry_seconds

    async def process_next(self) -> bool:
        item = await self._repository.claim_next()
        if item is None:
            return False

        if _is_expired(item, self._ttl_minutes):
            await self._repository.mark_dropped(item.id, "expired")
            return True

        request = PromptBuildRequest.from_payload(item.payload)
        session_id = item.payload.get("session_id")
        cycle_number = item.payload.get("cycle_number")
        execution_mode = normalize_execution_mode(item.payload.get("execution_mode"))
        deadline = _deadline(item, self._ttl_minutes)
        attempts = 0

        def _with_session(payload: dict) -> dict:
            if session_id:
                payload = dict(payload)
                payload["session_id"] = session_id
            return payload

        await self._outbox.enqueue_event(
            topics.PROMPT_STARTED,
            _with_session(
                {
                    "request_id": request.request_id,
                    "tickers": request.tickers,
                    "intervals": request.intervals,
                    "trigger_reason": request.trigger_reason,
                    "template_id": request.template_id,
                    "execution_mode": execution_mode.value,
                    "cycle_number": cycle_number,
                }
            ),
        )

        while True:
            try:
                result = await self._prompt_builder.build(request)
                result_payload = result.to_dict()
                queued_for_llm = should_enqueue_llm(execution_mode)
                result_payload["execution_mode"] = execution_mode.value
                result_payload["queued_for_llm"] = queued_for_llm
                result_payload["provider"] = item.payload.get("provider")
                result_payload["prompt_chars"] = len(result.prompt_text or "")
                result_payload["cycle_number"] = cycle_number
                await self._repository.mark_done(item.id, result_payload)
                await self._outbox.enqueue_event(
                    topics.PROMPT_COMPLETED,
                    _with_session(result_payload),
                )

                if not queued_for_llm:
                    return True

                model = item.payload.get("model")
                provider = item.payload.get("provider")
                reasoning_effort = item.payload.get("reasoning_effort")

                await self._llm_queue.enqueue(
                    {
                        "request_id": request.request_id,
                        "session_id": session_id,
                        "prompt_text": result.prompt_text,
                        "data": result.data,
                        "trace_id": request.trace_id,
                        "template_id": result.template_id,
                        "execution_mode": execution_mode.value,
                        "model": model,
                        "provider": provider,
                        "reasoning_effort": reasoning_effort,
                        "tickers": request.tickers,
                        "cycle_number": item.payload.get("cycle_number"),
                    }
                )
                return True
            except PromptBuildError as exc:
                if "missing quant snapshots" not in str(exc).lower():
                    await self._repository.mark_failed(item.id, str(exc))
                    await self._outbox.enqueue_event(
                        topics.PROMPT_FAILED,
                        _with_session(
                            {
                                "request_id": request.request_id,
                                "error": str(exc),
                                "cycle_number": cycle_number,
                            }
                        ),
                    )
                    return True
                if datetime.now(timezone.utc) >= deadline:
                    await self._repository.mark_failed(item.id, "quant_data_timeout")
                    await self._outbox.enqueue_event(
                        topics.PROMPT_FAILED,
                        _with_session(
                            {
                                "request_id": request.request_id,
                                "error": "quant_data_timeout",
                                "cycle_number": cycle_number,
                            }
                        ),
                    )
                    return True
                attempts += 1
                await self._outbox.enqueue_event(
                    topics.PROMPT_WAITING_QUANT,
                    _with_session(
                        {
                            "request_id": request.request_id,
                            "attempt": attempts,
                            "retry_in_seconds": self._quant_retry_seconds,
                            "cycle_number": cycle_number,
                        }
                    ),
                )
                await asyncio.sleep(self._quant_retry_seconds)
            except Exception as exc:  # pragma: no cover
                await self._repository.mark_failed(item.id, f"unexpected_error: {exc}")
                await self._outbox.enqueue_event(
                    topics.PROMPT_FAILED,
                    _with_session(
                        {
                            "request_id": request.request_id,
                            "error": f"unexpected_error: {exc}",
                            "cycle_number": cycle_number,
                        }
                    ),
                )
                return True


def _deadline(item: PromptBuildQueueItem, ttl_minutes: int) -> datetime:
    if item.expires_at is not None:
        return item.expires_at
    return item.created_at + timedelta(minutes=ttl_minutes)


def _is_expired(item: PromptBuildQueueItem, ttl_minutes: int) -> bool:
    return datetime.now(timezone.utc) > _deadline(item, ttl_minutes)
