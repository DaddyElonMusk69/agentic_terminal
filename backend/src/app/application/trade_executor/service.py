from typing import Optional

from app.domain.llm_response_worker.models import ExecutionIdea
from app.domain.trade_executor.models import ExecutionResult
from app.infrastructure.exchange.ccxt_trade_executor import CCXTTradeConfig, CCXTTradeExecutor
from app.domain.portfolio.interfaces import ExchangeRepository


class TradeExecutorService:
    def __init__(self, repository: ExchangeRepository) -> None:
        self._repository = repository

    async def execute(self, decision: ExecutionIdea) -> ExecutionResult:
        account = await self._repository.get_active_account()
        if not account:
            return ExecutionResult(success=False, status="no_account", error="No active account configured")

        credentials = await self._repository.get_credentials(account.id)
        if not credentials:
            return ExecutionResult(success=False, status="no_credentials", error="Missing credentials for account")

        config = CCXTTradeConfig(
            exchange_id=account.exchange,
            api_key=credentials.api_key,
            api_secret=credentials.api_secret,
            passphrase=credentials.passphrase,
            is_testnet=account.is_testnet,
        )

        async with CCXTTradeExecutor(config) as executor:
            return await executor.execute(decision)
