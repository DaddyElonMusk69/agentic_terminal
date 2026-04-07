from typing import Optional

from app.domain.llm_response_worker.models import ExecutionIdea
from app.domain.trade_executor.models import ExecutionResult
from app.infrastructure.exchange.ccxt_trade_executor import CCXTTradeConfig, CCXTTradeExecutor
from app.domain.portfolio.interfaces import ExchangeRepository


class TradeExecutorService:
    def __init__(self, repository: ExchangeRepository) -> None:
        self._repository = repository

    async def execute(self, decision: ExecutionIdea) -> ExecutionResult:
        try:
            executor = await self._get_executor()
        except KeyError as exc:
            status = "no_account" if "active account" in str(exc).lower() else "no_credentials"
            return ExecutionResult(success=False, status=status, error=str(exc))
        async with executor:
            return await executor.execute(decision)

    async def place_stop_market_entry(
        self,
        *,
        symbol: str,
        side: str,
        size_usd: float,
        trigger_price: float,
        leverage: int,
    ) -> ExecutionResult:
        try:
            executor = await self._get_executor()
        except KeyError as exc:
            status = "no_account" if "active account" in str(exc).lower() else "no_credentials"
            return ExecutionResult(success=False, status=status, error=str(exc))
        async with executor:
            return await executor.place_open_stop_market(
                symbol=symbol,
                side=side,
                size_usd=size_usd,
                trigger_price=trigger_price,
                leverage=leverage,
            )

    async def _get_executor(self) -> CCXTTradeExecutor:
        account = await self._repository.get_active_account()
        if not account:
            raise KeyError("No active account configured")

        credentials = await self._repository.get_credentials(account.id)
        if not credentials:
            raise KeyError("Missing credentials for account")

        config = CCXTTradeConfig(
            exchange_id=account.exchange,
            api_key=credentials.api_key,
            api_secret=credentials.api_secret,
            passphrase=credentials.passphrase,
            is_testnet=account.is_testnet,
        )
        return CCXTTradeExecutor(config)
