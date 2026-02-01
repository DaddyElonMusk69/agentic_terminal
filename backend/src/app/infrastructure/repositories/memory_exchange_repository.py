import asyncio
from datetime import datetime, timezone
from typing import Dict, Optional, List

from app.domain.portfolio.models import ExchangeAccount, ExchangeCredentials
from app.domain.portfolio.interfaces import ExchangeRepository
from app.infrastructure.crypto.cipher import PlaintextCipher, SecretCipher


class InMemoryExchangeRepository(ExchangeRepository):
    """In-memory repository for early development and testing."""

    def __init__(self, cipher: Optional[SecretCipher] = None) -> None:
        self._cipher = cipher or PlaintextCipher()
        self._accounts: Dict[str, ExchangeAccount] = {}
        self._credentials: Dict[str, Dict[str, str]] = {}
        self._active_id: Optional[str] = None
        self._lock = asyncio.Lock()

    async def list_accounts(self) -> List[ExchangeAccount]:
        async with self._lock:
            return list(self._accounts.values())

    async def get_account(self, account_id: str) -> Optional[ExchangeAccount]:
        async with self._lock:
            return self._accounts.get(account_id)

    async def create_account(
        self,
        account: ExchangeAccount,
        credentials: ExchangeCredentials,
    ) -> ExchangeAccount:
        async with self._lock:
            self._accounts[account.id] = account
            self._credentials[account.id] = {
                "api_key": self._cipher.encrypt(credentials.api_key),
                "api_secret": self._cipher.encrypt(credentials.api_secret),
                "passphrase": self._cipher.encrypt(credentials.passphrase or ""),
                "agent_key": self._cipher.encrypt(credentials.agent_key or ""),
            }
            if account.is_active:
                self._active_id = account.id
            return account

    async def update_account(self, account: ExchangeAccount) -> ExchangeAccount:
        async with self._lock:
            if account.id not in self._accounts:
                raise KeyError(f"Account {account.id} not found")
            self._accounts[account.id] = account
            if account.is_active:
                self._active_id = account.id
            return account

    async def delete_account(self, account_id: str) -> None:
        async with self._lock:
            self._accounts.pop(account_id, None)
            self._credentials.pop(account_id, None)
            if self._active_id == account_id:
                self._active_id = None

    async def set_active(self, account_id: str) -> ExchangeAccount:
        async with self._lock:
            if account_id not in self._accounts:
                raise KeyError(f"Account {account_id} not found")
            updated = []
            for account in self._accounts.values():
                is_active = account.id == account_id
                updated.append(self._with_active(account, is_active))
            self._accounts = {a.id: a for a in updated}
            self._active_id = account_id
            return self._accounts[account_id]

    async def clear_active(self) -> None:
        async with self._lock:
            updated = []
            for account in self._accounts.values():
                updated.append(self._with_active(account, False))
            self._accounts = {a.id: a for a in updated}
            self._active_id = None

    async def get_active_account(self) -> Optional[ExchangeAccount]:
        async with self._lock:
            if not self._active_id:
                return None
            return self._accounts.get(self._active_id)

    async def get_credentials(self, account_id: str) -> Optional[ExchangeCredentials]:
        async with self._lock:
            raw = self._credentials.get(account_id)
            if not raw:
                return None
            return ExchangeCredentials(
                account_id=account_id,
                api_key=self._cipher.decrypt(raw["api_key"]),
                api_secret=self._cipher.decrypt(raw["api_secret"]),
                passphrase=self._cipher.decrypt(raw["passphrase"]) or None,
                agent_key=self._cipher.decrypt(raw.get("agent_key") or "") or None,
            )

    def _with_active(self, account: ExchangeAccount, is_active: bool) -> ExchangeAccount:
        return ExchangeAccount(
            id=account.id,
            name=account.name,
            exchange=account.exchange,
            is_active=is_active,
            is_testnet=account.is_testnet,
            created_at=account.created_at,
            updated_at=datetime.now(timezone.utc),
            wallet_address=account.wallet_address,
            validation_status=account.validation_status,
            last_validated_at=account.last_validated_at,
            validation_error=account.validation_error,
        )
