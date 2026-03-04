import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.application.automation.llm_queue_worker import LlmQueueWorker
from app.application.automation import topics
from app.domain.ai_providers.models import ProviderConfig
from app.domain.llm_caller.models import LlmCallResponse
from app.domain.llm_pipeline.models import LlmExecutionResult
from app.domain.llm_response_worker.models import LlmResponseParseResult
from app.infrastructure.external.codex_temp_images import CodexTempImageStore
from app.infrastructure.repositories.llm_queue_repository import LlmQueueItem


class StubLlmQueueRepository:
    def __init__(self, item: LlmQueueItem | None) -> None:
        self._item = item
        self.done_result = None
        self.failed_error = None
        self.dropped_reason = None

    async def claim_next(self):
        item = self._item
        self._item = None
        return item

    async def mark_done(self, request_id: str, result: dict):
        self.done_result = (request_id, result)

    async def mark_failed(self, request_id: str, error: str):
        self.failed_error = (request_id, error)

    async def mark_dropped(self, request_id: str, reason: str):
        self.dropped_reason = (request_id, reason)


class StubLlmPipeline:
    def __init__(self, result: LlmExecutionResult) -> None:
        self._result = result
        self.last_kwargs = None

    async def execute(self, request, **kwargs):
        self.last_kwargs = kwargs
        return self._result


class FailingLlmPipeline:
    async def execute(self, request, **kwargs):
        raise RuntimeError("")


class StubOrderQueue:
    def __init__(self) -> None:
        self.items = []

    async def enqueue(self, payload: dict):
        self.items.append(payload)


class StubOutbox:
    def __init__(self) -> None:
        self.events = []

    async def enqueue_event(self, topic: str, payload: dict):
        self.events.append((topic, payload))


class StubProviderRepository:
    def __init__(self) -> None:
        self.configs: dict[str, ProviderConfig] = {}

    async def list_configs(self):
        return list(self.configs.values())

    async def get_config(self, provider: str):
        return self.configs.get(provider)

    async def upsert(self, config: ProviderConfig):
        self.configs[config.provider] = config
        return config

    async def delete(self, provider: str):
        self.configs.pop(provider, None)


def _build_queue_item(payload: dict) -> LlmQueueItem:
    return LlmQueueItem(
        id="req-1",
        payload=payload,
        status="queued",
        created_at=datetime.now(timezone.utc),
        expires_at=None,
    )


def _build_execution_result(success: bool, image_paths: list[str]) -> LlmExecutionResult:
    parse_result = LlmResponseParseResult(
        success=success,
        ideas=[],
        considerations=[],
        error=None if success else "parse_failed",
    )
    response = LlmCallResponse(
        content="JSON_ARRAY []",
        model="gpt-5.3-codex",
        tokens_used=12,
        latency_ms=4.0,
        raw_response={
            "protocol": "codex_cli",
            "image_paths": image_paths,
        },
    )
    return LlmExecutionResult(call_response=response, parse_result=parse_result)


@pytest.mark.asyncio
async def test_codex_success_deletes_images_and_persists_discovery(tmp_path: Path):
    image_path = tmp_path / "to_delete.png"
    image_path.write_bytes(b"img")

    payload = {
        "request_id": "req-1",
        "provider": "codex",
        "model": "gpt-5.3-codex",
        "prompt_text": "Analyze",
        "data": {"chart_snapshots": [{"type": "input_image", "image_url": str(image_path)}]},
    }
    repository = StubLlmQueueRepository(_build_queue_item(payload))
    pipeline = StubLlmPipeline(_build_execution_result(success=True, image_paths=[str(image_path)]))
    provider_repo = StubProviderRepository()

    worker = LlmQueueWorker(
        repository=repository,
        llm_pipeline=pipeline,
        order_queue=StubOrderQueue(),
        outbox=StubOutbox(),
        provider_repository=provider_repo,
    )
    worker._codex_temp_images = CodexTempImageStore(tmp_path)
    worker._codex_sweep_interval_seconds = 3600

    handled = await worker.process_next()

    assert handled is True
    assert not image_path.exists()
    assert repository.done_result is not None
    assert pipeline.last_kwargs["protocol"] == "codex_cli"
    saved = await provider_repo.get_config("codex")
    assert saved is not None
    assert saved.settings["codex_last_success_model"] == "gpt-5.3-codex"


@pytest.mark.asyncio
async def test_codex_parse_failure_keeps_images(tmp_path: Path):
    image_path = tmp_path / "keep.png"
    image_path.write_bytes(b"img")

    payload = {
        "request_id": "req-1",
        "provider": "codex",
        "model": "gpt-5.3-codex",
        "prompt_text": "Analyze",
        "data": {"chart_snapshots": [{"type": "input_image", "image_url": str(image_path)}]},
    }
    repository = StubLlmQueueRepository(_build_queue_item(payload))
    pipeline = StubLlmPipeline(_build_execution_result(success=False, image_paths=[str(image_path)]))
    provider_repo = StubProviderRepository()

    worker = LlmQueueWorker(
        repository=repository,
        llm_pipeline=pipeline,
        order_queue=StubOrderQueue(),
        outbox=StubOutbox(),
        provider_repository=provider_repo,
    )
    worker._codex_temp_images = CodexTempImageStore(tmp_path)
    worker._codex_sweep_interval_seconds = 3600

    handled = await worker.process_next()

    assert handled is True
    assert image_path.exists()
    assert repository.failed_error is not None
    saved = await provider_repo.get_config("codex")
    assert saved is not None


@pytest.mark.asyncio
async def test_codex_periodic_sweep_runs_even_without_queue_item(tmp_path: Path):
    old_file = tmp_path / "stale.png"
    old_file.write_bytes(b"stale")
    old_ts = time.time() - (4 * 3600)
    os.utime(old_file, (old_ts, old_ts))

    repository = StubLlmQueueRepository(None)
    worker = LlmQueueWorker(
        repository=repository,
        llm_pipeline=StubLlmPipeline(_build_execution_result(success=True, image_paths=[])),
        order_queue=StubOrderQueue(),
        outbox=StubOutbox(),
        provider_repository=StubProviderRepository(),
    )
    worker._codex_temp_images = CodexTempImageStore(tmp_path)
    worker._codex_temp_ttl_minutes = 60
    worker._codex_sweep_interval_seconds = 0
    worker._last_codex_sweep_at = None

    handled = await worker.process_next()

    assert handled is False
    assert not old_file.exists()


@pytest.mark.asyncio
async def test_codex_exception_emits_non_empty_error_and_metadata():
    payload = {
        "request_id": "req-1",
        "provider": "codex",
        "model": "gpt-5.3-codex",
        "prompt_text": "Analyze",
        "data": {"chart_snapshots": []},
    }
    repository = StubLlmQueueRepository(_build_queue_item(payload))
    outbox = StubOutbox()
    worker = LlmQueueWorker(
        repository=repository,
        llm_pipeline=FailingLlmPipeline(),
        order_queue=StubOrderQueue(),
        outbox=outbox,
        provider_repository=StubProviderRepository(),
    )

    handled = await worker.process_next()

    assert handled is True
    assert repository.failed_error is not None
    assert repository.failed_error[1] == "RuntimeError"
    failed_events = [payload for topic, payload in outbox.events if topic == topics.LLM_FAILED]
    assert len(failed_events) == 1
    event_payload = failed_events[0]
    assert event_payload["error"] == "RuntimeError"
    assert event_payload["provider"] == "codex"
    assert event_payload["protocol"] == "codex_cli"
    assert event_payload["model"] == "gpt-5.3-codex"


@pytest.mark.asyncio
async def test_missing_provider_with_codex_model_infers_codex_protocol(tmp_path: Path):
    image_path = tmp_path / "to_delete.png"
    image_path.write_bytes(b"img")

    payload = {
        "request_id": "req-1",
        "provider": None,
        "model": "gpt-5.3-codex",
        "prompt_text": "Analyze",
        "data": {"chart_snapshots": [{"type": "input_image", "image_url": str(image_path)}]},
    }
    repository = StubLlmQueueRepository(_build_queue_item(payload))
    pipeline = StubLlmPipeline(_build_execution_result(success=True, image_paths=[str(image_path)]))
    outbox = StubOutbox()
    provider_repo = StubProviderRepository()

    worker = LlmQueueWorker(
        repository=repository,
        llm_pipeline=pipeline,
        order_queue=StubOrderQueue(),
        outbox=outbox,
        provider_repository=provider_repo,
    )
    worker._codex_temp_images = CodexTempImageStore(tmp_path)
    worker._codex_sweep_interval_seconds = 3600

    handled = await worker.process_next()

    assert handled is True
    assert repository.done_result is not None
    assert pipeline.last_kwargs["protocol"] == "codex_cli"
    assert pipeline.last_kwargs["provider"] == "codex"
    requested_events = [evt for evt in outbox.events if evt[0] == topics.LLM_REQUESTED]
    assert len(requested_events) == 1
    assert requested_events[0][1]["protocol"] == "codex_cli"
    assert requested_events[0][1]["provider"] == "codex"
