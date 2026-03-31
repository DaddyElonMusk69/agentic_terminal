from datetime import datetime
from typing import Protocol, Any, Dict, List, Optional

from app.domain.portfolio.models import (
    AccountSetup,
    ExchangeAccount,
    ExchangeCredentials,
    AccountState,
    Position,
    MarketCandle,
    MarketDataPoint,
    MarketQuote,
    OrderBookSnapshot,
    FundingRateSnapshot,
    DailyPnlSnapshot,
)


class ExchangeRepository(Protocol):
    async def list_accounts(self) -> List[ExchangeAccount]:
        ...

    async def get_account(self, account_id: str) -> Optional[ExchangeAccount]:
        ...

    async def create_account(
        self,
        account: ExchangeAccount,
        credentials: ExchangeCredentials,
    ) -> ExchangeAccount:
        ...

    async def update_account(self, account: ExchangeAccount) -> ExchangeAccount:
        ...

    async def delete_account(self, account_id: str) -> None:
        ...

    async def set_active(self, account_id: str) -> ExchangeAccount:
        ...

    async def clear_active(self) -> None:
        ...

    async def get_active_account(self) -> Optional[ExchangeAccount]:
        ...

    async def get_credentials(self, account_id: str) -> Optional[ExchangeCredentials]:
        ...


class AccountSetupRepository(Protocol):
    async def get_setup(self) -> Optional[AccountSetup]:
        ...

    async def set_setup(self, setup: AccountSetup) -> AccountSetup:
        ...


class ExchangeConnector(Protocol):
    async def fetch_account_state(self) -> AccountState:
        ...

    async def fetch_positions(self) -> List[Position]:
        ...

    async def fetch_open_orders(self, symbols: Optional[List[str]] = None) -> List[dict]:
        ...

    async def fetch_order(self, order_id: str, symbol: str) -> Optional[dict]:
        ...

    async def cancel_order(self, order_id: str, symbol: str) -> Optional[dict]:
        ...

    async def fetch_recent_trades(
        self,
        limit: int = 10,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[dict]:
        ...

    async def fetch_recent_completed_trades(
        self,
        limit: int = 10,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[dict]:
        ...

    async def fetch_candles(self, symbol: str, timeframe: str, limit: int) -> List[MarketCandle]:
        ...

    async def fetch_ticker_price(self, symbol: str) -> float | None:
        ...

    async def fetch_ticker_quote(self, symbol: str) -> Optional[MarketQuote]:
        ...

    async def fetch_ticker_quotes(self, symbols: List[str]) -> Dict[str, MarketQuote]:
        ...

    async def fetch_open_interest_history(
        self, symbol: str, timeframe: str, limit: int
    ) -> List[MarketDataPoint]:
        ...

    async def fetch_order_book(
        self, symbol: str, limit: int = 50
    ) -> Optional[OrderBookSnapshot]:
        ...

    async def fetch_funding_rate(self, symbol: str) -> Optional[FundingRateSnapshot]:
        ...

    async def fetch_daily_pnl(self) -> DailyPnlSnapshot:
        ...

    async def fetch_market_limits(self, symbol: str) -> Dict[str, Any] | None:
        ...


class ConnectorFactory(Protocol):
    def create(
        self,
        account: ExchangeAccount,
        credentials: ExchangeCredentials,
    ) -> ExchangeConnector:
        ...
