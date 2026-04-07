import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple, Dict
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
    OPEN_ORDERS_CACHE_TTL_SECONDS = 1.0
    DAILY_PNL_CACHE_TTL_SECONDS = 10.0

    def __init__(self, repository: ExchangeRepository, connector_factory: ConnectorFactory) -> None:
        self._repo = repository
        self._factory = connector_factory
        self._open_orders_cache: Dict[Tuple[str, Tuple[str, ...], bool], Tuple[datetime, List[dict]]] = {}
        self._open_orders_inflight: Dict[
            Tuple[str, Tuple[str, ...], bool], asyncio.Task[List[dict]]
        ] = {}
        self._open_orders_lock = asyncio.Lock()
        self._daily_pnl_cache: Dict[str, Tuple[datetime, DailyPnlSnapshot]] = {}
        self._daily_pnl_inflight: Dict[str, asyncio.Task[DailyPnlSnapshot]] = {}
        self._daily_pnl_lock = asyncio.Lock()

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

    async def get_positions(self):
        account = await self._repo.get_active_account()
        if not account:
            raise KeyError("No active account configured")
        connector = await self.get_active_connector()
        return await connector.fetch_positions()

    async def get_daily_pnl(self) -> DailyPnlSnapshot:
        account = await self._repo.get_active_account()
        if not account:
            raise KeyError("No active account configured")
        account_id = account.id
        now = datetime.now(timezone.utc)

        async with self._daily_pnl_lock:
            cached = self._daily_pnl_cache.get(account_id)
            if cached is not None:
                cached_at, cached_snapshot = cached
                if now - cached_at <= timedelta(seconds=self.DAILY_PNL_CACHE_TTL_SECONDS):
                    return cached_snapshot
            inflight = self._daily_pnl_inflight.get(account_id)
            if inflight is None:
                inflight = asyncio.create_task(self._fetch_daily_pnl_uncached(account))
                self._daily_pnl_inflight[account_id] = inflight

        try:
            snapshot = await inflight
        except Exception:
            async with self._daily_pnl_lock:
                if self._daily_pnl_inflight.get(account_id) is inflight:
                    self._daily_pnl_inflight.pop(account_id, None)
            raise

        async with self._daily_pnl_lock:
            if self._daily_pnl_inflight.get(account_id) is inflight:
                self._daily_pnl_inflight.pop(account_id, None)
            self._daily_pnl_cache[account_id] = (datetime.now(timezone.utc), snapshot)

        return snapshot

    async def get_open_orders(
        self,
        symbols: Optional[List[str]] = None,
        *,
        include_conditional_orders: bool = True,
    ) -> List[dict]:
        account = await self._repo.get_active_account()
        if not account:
            raise KeyError("No active account configured")
        normalized_symbols = _normalize_open_order_symbols(symbols)
        cache_key = (account.id, normalized_symbols, bool(include_conditional_orders))
        now = datetime.now(timezone.utc)

        async with self._open_orders_lock:
            cached = self._open_orders_cache.get(cache_key)
            if cached is not None:
                cached_at, cached_orders = cached
                if now - cached_at <= timedelta(seconds=self.OPEN_ORDERS_CACHE_TTL_SECONDS):
                    return list(cached_orders)
            inflight = self._open_orders_inflight.get(cache_key)
            if inflight is None:
                inflight = asyncio.create_task(
                    self._fetch_open_orders_uncached(
                        list(normalized_symbols) or None,
                        include_conditional_orders=include_conditional_orders,
                    )
                )
                self._open_orders_inflight[cache_key] = inflight

        try:
            fetched_orders = await inflight
        except Exception:
            async with self._open_orders_lock:
                if self._open_orders_inflight.get(cache_key) is inflight:
                    self._open_orders_inflight.pop(cache_key, None)
            raise

        async with self._open_orders_lock:
            if self._open_orders_inflight.get(cache_key) is inflight:
                self._open_orders_inflight.pop(cache_key, None)
            self._open_orders_cache[cache_key] = (datetime.now(timezone.utc), list(fetched_orders))

        return list(fetched_orders)

    async def get_order(self, order_id: str, symbol: str) -> Optional[dict]:
        connector = await self.get_active_connector()
        fetcher = getattr(connector, "fetch_order", None)
        if not callable(fetcher):
            return None
        return await fetcher(order_id, symbol)

    async def cancel_order(self, order_id: str, symbol: str) -> Optional[dict]:
        account = await self._repo.get_active_account()
        connector = await self.get_active_connector()
        fetcher = getattr(connector, "cancel_order", None)
        if not callable(fetcher):
            return None
        result = await fetcher(order_id, symbol)
        await self._invalidate_open_orders_cache(account.id if account else None)
        return result

    async def get_ticker_quotes(self, symbols: List[str]) -> dict:
        connector = await self.get_active_connector()
        fetcher = getattr(connector, "fetch_ticker_quotes", None)
        if not callable(fetcher):
            return {}
        return await fetcher(symbols)

    async def get_candles(self, symbol: str, timeframe: str, limit: int):
        connector = await self.get_active_connector()
        fetcher = getattr(connector, "fetch_candles", None)
        if not callable(fetcher):
            return []
        return await fetcher(symbol, timeframe, limit)

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

    async def _fetch_open_orders_uncached(
        self,
        symbols: Optional[List[str]],
        *,
        include_conditional_orders: bool,
    ) -> List[dict]:
        connector = await self.get_active_connector()
        fetcher = getattr(connector, "fetch_open_orders", None)
        if not callable(fetcher):
            return []
        return await fetcher(
            symbols,
            include_conditional_orders=include_conditional_orders,
        )

    async def _fetch_daily_pnl_uncached(self, account: ExchangeAccount) -> DailyPnlSnapshot:
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

    async def _invalidate_open_orders_cache(self, account_id: Optional[str] = None) -> None:
        async with self._open_orders_lock:
            if account_id is None:
                self._open_orders_cache.clear()
                self._open_orders_inflight.clear()
                return
            for key in list(self._open_orders_cache.keys()):
                if key[0] == account_id:
                    self._open_orders_cache.pop(key, None)
            for key in list(self._open_orders_inflight.keys()):
                if key[0] == account_id:
                    self._open_orders_inflight.pop(key, None)


def _normalize_open_order_symbols(symbols: Optional[List[str]]) -> Tuple[str, ...]:
    if not symbols:
        return tuple()
    normalized = {str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()}
    return tuple(sorted(normalized))

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
