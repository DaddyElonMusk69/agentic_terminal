from datetime import datetime, timezone

import pytest

from app.application.automation import topics
from app.application.automation.llm_queue_worker import LlmQueueWorker
from app.domain.automation.models import AutomationConfig
from app.domain.llm_caller.models import LlmCallResponse
from app.domain.llm_pipeline.models import LlmExecutionResult
from app.domain.llm_response_worker.models import ExecutionAction, ExecutionIdea, LlmResponseParseResult
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

    async def execute(self, request, **kwargs):  # noqa: ANN001
        return self._result


class StubOrderQueue:
    def __init__(self) -> None:
        self.items: list[dict] = []

    async def enqueue(self, payload: dict):
        self.items.append(payload)


class StubOutbox:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def enqueue_event(self, topic: str, payload: dict):
        self.events.append((topic, payload))


class StubAutomationConfigService:
    def __init__(self, reverse_order_enabled: bool, should_raise: bool = False) -> None:
        self._reverse_order_enabled = reverse_order_enabled
        self._should_raise = should_raise

    async def get_config(self) -> AutomationConfig:
        if self._should_raise:
            raise RuntimeError("config unavailable")
        return AutomationConfig(
            execution_mode="dry_run",
            ema_interval_seconds=60,
            quant_interval_seconds=60,
            pending_entry_timeout_seconds=900,
            max_positions=3,
            provider=None,
            model=None,
            reverse_order_enabled=self._reverse_order_enabled,
        )


def _build_queue_item() -> LlmQueueItem:
    return LlmQueueItem(
        id="req-1",
        payload={
            "request_id": "req-1",
            "prompt_text": "Analyze",
            "data": {},
            "execution_mode": "dry_run",
            "cycle_number": 8,
        },
        status="queued",
        created_at=datetime.now(timezone.utc),
        expires_at=None,
    )


def _build_execution_result() -> LlmExecutionResult:
    ideas = [
        ExecutionIdea(action=ExecutionAction.OPEN_LONG, symbol="BTC", position_size_usd=100),
        ExecutionIdea(action=ExecutionAction.OPEN_SHORT_LIMIT, symbol="ETH", position_size_usd=100),
        ExecutionIdea(action=ExecutionAction.CLOSE, symbol="SOL"),
    ]
    parse_result = LlmResponseParseResult(success=True, ideas=ideas, considerations=[])
    response = LlmCallResponse(
        content='[{"action":"OPEN_LONG","symbol":"BTC"}]',
        model="gpt-5",
        tokens_used=12,
        latency_ms=10.0,
    )
    return LlmExecutionResult(call_response=response, parse_result=parse_result)


def _event_payload(events: list[tuple[str, dict]], topic: str) -> dict:
    for event_topic, payload in events:
        if event_topic == topic:
            return payload
    raise AssertionError(f"missing event {topic}")


@pytest.mark.asyncio
async def test_reverse_order_enabled_flips_open_actions_and_emits_metadata():
    repository = StubLlmQueueRepository(_build_queue_item())
    order_queue = StubOrderQueue()
    outbox = StubOutbox()
    worker = LlmQueueWorker(
        repository=repository,
        llm_pipeline=StubLlmPipeline(_build_execution_result()),
        order_queue=order_queue,
        outbox=outbox,
        automation_config_service=StubAutomationConfigService(True),
    )

    handled = await worker.process_next()

    assert handled is True
    assert repository.done_result is not None
    done_parse_ideas = repository.done_result[1]["parse_result"]["ideas"]
    assert [idea["action"] for idea in done_parse_ideas] == [
        "OPEN_SHORT",
        "OPEN_LONG_LIMIT",
        "CLOSE",
    ]

    queued_actions = [item["execution_idea"]["action"] for item in order_queue.items]
    assert queued_actions == ["OPEN_SHORT", "OPEN_LONG_LIMIT", "CLOSE"]

    parser_payload = _event_payload(outbox.events, topics.PARSER_COMPLETED)
    assert parser_payload["reverse_order_enabled"] is True
    assert parser_payload["reverse_order_applied"] is True
    assert parser_payload["reversed_actions"] == [
        {"symbol": "BTC", "original_action": "OPEN_LONG", "effective_action": "OPEN_SHORT"},
        {
            "symbol": "ETH",
            "original_action": "OPEN_SHORT_LIMIT",
            "effective_action": "OPEN_LONG_LIMIT",
        },
    ]

    order_events = [payload for topic, payload in outbox.events if topic == topics.ORDER_QUEUED]
    assert len(order_events) == 3
    assert order_events[0]["original_action"] == "OPEN_LONG"
    assert order_events[0]["effective_action"] == "OPEN_SHORT"
    assert order_events[0]["reverse_order_applied"] is True
    assert order_events[2]["original_action"] == "CLOSE"
    assert order_events[2]["effective_action"] == "CLOSE"
    assert order_events[2]["reverse_order_applied"] is False


@pytest.mark.asyncio
async def test_reverse_order_disabled_keeps_actions_unchanged():
    repository = StubLlmQueueRepository(_build_queue_item())
    order_queue = StubOrderQueue()
    outbox = StubOutbox()
    worker = LlmQueueWorker(
        repository=repository,
        llm_pipeline=StubLlmPipeline(_build_execution_result()),
        order_queue=order_queue,
        outbox=outbox,
        automation_config_service=StubAutomationConfigService(False),
    )

    handled = await worker.process_next()

    assert handled is True
    done_parse_ideas = repository.done_result[1]["parse_result"]["ideas"]
    assert [idea["action"] for idea in done_parse_ideas] == [
        "OPEN_LONG",
        "OPEN_SHORT_LIMIT",
        "CLOSE",
    ]

    parser_payload = _event_payload(outbox.events, topics.PARSER_COMPLETED)
    assert parser_payload["reverse_order_enabled"] is False
    assert parser_payload["reverse_order_applied"] is False
    assert parser_payload["reversed_actions"] == []


@pytest.mark.asyncio
async def test_reverse_order_falls_back_to_disabled_when_config_lookup_fails():
    repository = StubLlmQueueRepository(_build_queue_item())
    outbox = StubOutbox()
    worker = LlmQueueWorker(
        repository=repository,
        llm_pipeline=StubLlmPipeline(_build_execution_result()),
        order_queue=StubOrderQueue(),
        outbox=outbox,
        automation_config_service=StubAutomationConfigService(False, should_raise=True),
    )

    handled = await worker.process_next()

    assert handled is True
    done_parse_ideas = repository.done_result[1]["parse_result"]["ideas"]
    assert [idea["action"] for idea in done_parse_ideas] == [
        "OPEN_LONG",
        "OPEN_SHORT_LIMIT",
        "CLOSE",
    ]
    parser_payload = _event_payload(outbox.events, topics.PARSER_COMPLETED)
    assert parser_payload["reverse_order_enabled"] is False
    assert parser_payload["reverse_order_applied"] is False
