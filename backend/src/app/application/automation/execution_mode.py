from __future__ import annotations

from enum import Enum
from typing import Optional


class ExecutionMode(str, Enum):
    PROMPT_TEST = "prompt_test"
    DRY_RUN = "dry_run"
    PRODUCTION = "production"


def normalize_execution_mode(value: Optional[str]) -> ExecutionMode:
    if isinstance(value, ExecutionMode):
        return value
    if not value:
        return ExecutionMode.DRY_RUN
    normalized = value.strip().lower()
    for mode in ExecutionMode:
        if mode.value == normalized:
            return mode
    return ExecutionMode.DRY_RUN


def should_enqueue_llm(mode: ExecutionMode) -> bool:
    return mode != ExecutionMode.PROMPT_TEST


def should_enqueue_orders(mode: ExecutionMode) -> bool:
    return mode != ExecutionMode.PROMPT_TEST


def should_execute_trades(mode: ExecutionMode) -> bool:
    return mode == ExecutionMode.PRODUCTION
