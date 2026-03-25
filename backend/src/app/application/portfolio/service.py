from dataclasses import replace
from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from app.domain.portfolio.interfaces import ExchangeRepository, ConnectorFactory, ExchangeConnector
from app.domain.portfolio.models import (
    AccountState,
    ExchangeAccount,
    ExchangeCredentials,
    PortfolioSnapshot,
    DailyPnlSnapshot,
)


class PortfolioService:
    """Single source of truth for exchange accounts and portfolio data."""

    def __init__(self, repository: ExchangeRepository, connector_factory: ConnectorFactory) -> None:
        self._repo = repository
        self._factory = connector_factory

    async def list_accounts(self) -> List[ExchangeAccount]:
        return await self._repo.list_accounts()

    async def get_account(self, account_id: str) -> Optional[ExchangeAccount]:
        return await self._repo.get_account(account_id)

    async def get_active_account(self) -> Optional[ExchangeAccount]:
        return await self._repo.get_active_account()

    async def get_credentials(self, account_id: str) -> Optional[ExchangeCredentials]:
        return await self._repo.get_credentials(account_id)

    async def get_active_connector(self) -> ExchangeConnector:
        account = await self._repo.get_active_account()
        if not account:
            raise KeyError("No active account configured")

        credentials = await self._repo.get_credentials(account.id)
        if not credentials:
            raise KeyError("Missing credentials for active account")

        return self._factory.create(account, credentials)

    async def create_account(
        self,
        name: str,
        exchange: str,
        api_key: str,
        api_secret: str,
        passphrase: Optional[str],
        is_testnet: bool,
        wallet_address: Optional[str] = None,
        agent_key: Optional[str] = None,
    ) -> ExchangeAccount:
        now = datetime.now(timezone.utc)
        account = ExchangeAccount(
            id=str(uuid4()),
            name=name,
            exchange=exchange,
            is_active=False,
            is_testnet=is_testnet,
            created_at=now,
            updated_at=now,
            wallet_address=wallet_address,
        )
        credentials = ExchangeCredentials(
            account_id=account.id,
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,
            agent_key=agent_key,
        )
        return await self._repo.create_account(account, credentials)

    async def update_account(
        self,
        account_id: str,
        name: Optional[str],
        is_testnet: Optional[bool],
        wallet_address: Optional[str] = None,
    ) -> ExchangeAccount:
        account = await self._repo.get_account(account_id)
        if not account:
            raise KeyError(f"Account {account_id} not found")

        updated = ExchangeAccount(
            id=account.id,
            name=name or account.name,
            exchange=account.exchange,
            is_active=account.is_active,
            is_testnet=account.is_testnet if is_testnet is None else is_testnet,
            created_at=account.created_at,
            updated_at=datetime.now(timezone.utc),
            wallet_address=wallet_address if wallet_address is not None else account.wallet_address,
            validation_status=account.validation_status,
            last_validated_at=account.last_validated_at,
            validation_error=account.validation_error,
        )
        return await self._repo.update_account(updated)

    async def delete_account(self, account_id: str) -> None:
        return await self._repo.delete_account(account_id)

    async def activate_account(self, account_id: str) -> ExchangeAccount:
        return await self._repo.set_active(account_id)

    async def deactivate_account(self) -> None:
        await self._repo.clear_active()

    async def get_portfolio_snapshot(self) -> PortfolioSnapshot:
        account = await self._repo.get_active_account()
        if not account:
            raise KeyError("No active account configured")

        connector = await self.get_active_connector()
        state = await connector.fetch_account_state()
        positions = await connector.fetch_positions()

        state = AccountState(
            account_value=state.account_value,
            available_margin=state.available_margin,
            total_margin_used=state.total_margin_used,
            unrealized_pnl=state.unrealized_pnl,
            open_positions_count=len(positions),
            total_exposure_pct=state.total_exposure_pct,
        )

        return PortfolioSnapshot(
            account=account,
            state=state,
            positions=positions,
        )

    async def get_daily_pnl(self) -> DailyPnlSnapshot:
        account = await self._repo.get_active_account()
        if not account:
            raise KeyError("No active account configured")

        connector = await self.get_active_connector()
        snapshot = await connector.fetch_daily_pnl()
        if snapshot.exchange is None:
            snapshot = DailyPnlSnapshot(
                realized_pnl=snapshot.realized_pnl,
                trade_count=snapshot.trade_count,
                fills=snapshot.fills,
                exchange=account.exchange,
            )
        return snapshot

    async def get_open_orders(self, symbols: Optional[List[str]] = None) -> List[dict]:
        connector = await self.get_active_connector()
        fetcher = getattr(connector, "fetch_open_orders", None)
        if not callable(fetcher):
            return []
        return await fetcher(symbols)

    async def get_recent_trades(
        self,
        limit: int = 10,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[dict]:
        connector = await self.get_active_connector()
        fetcher = getattr(connector, "fetch_recent_trades", None)
        if not callable(fetcher):
            return []
        if start_time is not None or end_time is not None:
            try:
                return await fetcher(limit=limit, start_time=start_time, end_time=end_time)
            except TypeError:
                # Backward-compatible fallback for connectors that only accept limit.
                pass
        return await fetcher(limit)

    async def get_recent_completed_trades(
        self,
        limit: int = 10,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[dict]:
        connector = await self.get_active_connector()
        fetcher = getattr(connector, "fetch_recent_completed_trades", None)
        if not callable(fetcher):
            return []
        if start_time is not None or end_time is not None:
            try:
                return await fetcher(limit=limit, start_time=start_time, end_time=end_time)
            except TypeError:
                pass
        return await fetcher(limit)

    async def validate_account(self, account_id: str) -> ExchangeAccount:
        account = await self._repo.get_account(account_id)
        if not account:
            raise KeyError(f"Account {account_id} not found")

        credentials = await self._repo.get_credentials(account_id)
        if not credentials:
            raise KeyError("Missing credentials for account")

        now = datetime.now(timezone.utc)

        try:
            connector = self._factory.create(account, credentials)
            await connector.fetch_account_state()
            updated = replace(
                account,
                validation_status="valid",
                last_validated_at=now,
                validation_error=None,
                updated_at=now,
            )
        except Exception as exc:
            updated = replace(
                account,
                validation_status="invalid",
                last_validated_at=now,
                validation_error=str(exc),
                updated_at=now,
            )

        return await self._repo.update_account(updated)
