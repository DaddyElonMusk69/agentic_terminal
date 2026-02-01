from datetime import datetime
from typing import List, Optional, Protocol

from app.domain.automation_history.models import (
    AutomationSessionRecord,
    AutomationLogRecord,
    AutomationTradeRecord,
)


class AutomationSessionRepository(Protocol):
    async def create_session(
        self,
        session_id: str,
        execution_mode: str,
        provider: Optional[str],
        model: Optional[str],
        config_snapshot: Optional[dict],
    ) -> AutomationSessionRecord:
        ...

    async def get_by_id(self, session_id: str) -> Optional[AutomationSessionRecord]:
        ...

    async def list_all(self, limit: int, offset: int) -> List[AutomationSessionRecord]:
        ...

    async def count_all(self) -> int:
        ...

    async def end_session(
        self,
        session_id: str,
        ended_at: datetime,
        total_cycles: int,
        total_trades: int,
        total_pnl: float,
    ) -> Optional[AutomationSessionRecord]:
        ...

    async def increment_prompt_count(self, session_id: str, delta: int = 1) -> None:
        ...

    async def delete_session(self, session_id: str) -> bool:
        ...


class AutomationLogRepository(Protocol):
    async def create_log(
        self,
        session_id: str,
        log_type: str,
        data: Optional[dict],
        cycle_number: int = 0,
    ) -> AutomationLogRecord:
        ...

    async def list_by_session(
        self,
        session_id: str,
        limit: int,
        offset: int,
    ) -> List[AutomationLogRecord]:
        ...

    async def delete_by_session(self, session_id: str) -> int:
        ...


class AutomationTradeRepository(Protocol):
    async def create_trade(
        self,
        session_id: str,
        symbol: str,
        direction: Optional[str],
        action: Optional[str],
        entry_price: Optional[float],
        exit_price: Optional[float],
        size_usd: Optional[float],
        pnl: Optional[float],
        pnl_pct: Optional[float],
        status: Optional[str],
        closed_at: Optional[datetime],
        signal_data: Optional[dict],
        llm_reasoning: Optional[str],
        llm_response_full: Optional[str],
        order_id: Optional[str],
        fill_price: Optional[float],
        cycle_number: int = 0,
    ) -> AutomationTradeRecord:
        ...

    async def list_by_session(
        self,
        session_id: str,
    ) -> List[AutomationTradeRecord]:
        ...

    async def count_by_session(self, session_id: str) -> int:
        ...

    async def sum_pnl_by_session(self, session_id: str) -> float:
        ...

    async def delete_by_session(self, session_id: str) -> int:
        ...
