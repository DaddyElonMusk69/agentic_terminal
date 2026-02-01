from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.portfolio.interfaces import ExchangeRepository
from app.domain.portfolio.models import ExchangeAccount, ExchangeCredentials
from app.infrastructure.crypto.cipher import PlaintextCipher, SecretCipher
from app.infrastructure.db.models.exchange import ExchangeAccountModel, ExchangeCredentialModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SqlExchangeRepository(ExchangeRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], cipher: Optional[SecretCipher] = None) -> None:
        self._sessionmaker = sessionmaker
        self._cipher = cipher or PlaintextCipher()

    async def list_accounts(self) -> List[ExchangeAccount]:
        async with self._sessionmaker() as session:
            result = await session.execute(select(ExchangeAccountModel))
            return [self._to_account(row) for row in result.scalars().all()]

    async def get_account(self, account_id: str) -> Optional[ExchangeAccount]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(ExchangeAccountModel).where(ExchangeAccountModel.id == account_id)
            )
            model = result.scalar_one_or_none()
            return self._to_account(model) if model else None

    async def create_account(
        self,
        account: ExchangeAccount,
        credentials: ExchangeCredentials,
    ) -> ExchangeAccount:
        async with self._sessionmaker() as session:
            model = ExchangeAccountModel(
                id=account.id,
                name=account.name,
                exchange=account.exchange,
                is_active=account.is_active,
                is_testnet=account.is_testnet,
                wallet_address=account.wallet_address,
                validation_status=account.validation_status,
                last_validated_at=account.last_validated_at,
                validation_error=account.validation_error,
                created_at=account.created_at,
                updated_at=account.updated_at,
            )
            session.add(model)

            cred_model = ExchangeCredentialModel(
                account_id=account.id,
                api_key_encrypted=self._cipher.encrypt(credentials.api_key),
                api_secret_encrypted=self._cipher.encrypt(credentials.api_secret),
                passphrase_encrypted=self._cipher.encrypt(credentials.passphrase or "") or None,
                agent_key_encrypted=self._cipher.encrypt(credentials.agent_key or "") or None,
                created_at=account.created_at,
                updated_at=account.updated_at,
            )
            session.add(cred_model)

            if account.is_active:
                await self._deactivate_all(session)

            await session.commit()
            await session.refresh(model)
            return self._to_account(model)

    async def update_account(self, account: ExchangeAccount) -> ExchangeAccount:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(ExchangeAccountModel).where(ExchangeAccountModel.id == account.id)
            )
            model = result.scalar_one_or_none()
            if not model:
                raise KeyError(f"Account {account.id} not found")

            model.name = account.name
            model.is_testnet = account.is_testnet
            model.is_active = account.is_active
            model.wallet_address = account.wallet_address
            model.validation_status = account.validation_status
            model.last_validated_at = account.last_validated_at
            model.validation_error = account.validation_error
            model.updated_at = _utcnow()

            await session.commit()
            await session.refresh(model)
            return self._to_account(model)

    async def delete_account(self, account_id: str) -> None:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(ExchangeAccountModel).where(ExchangeAccountModel.id == account_id)
            )
            model = result.scalar_one_or_none()
            if model:
                await session.delete(model)
                await session.commit()

    async def set_active(self, account_id: str) -> ExchangeAccount:
        async with self._sessionmaker() as session:
            await self._deactivate_all(session)
            result = await session.execute(
                select(ExchangeAccountModel).where(ExchangeAccountModel.id == account_id)
            )
            model = result.scalar_one_or_none()
            if not model:
                raise KeyError(f"Account {account_id} not found")
            model.is_active = True
            model.updated_at = _utcnow()
            await session.commit()
            await session.refresh(model)
            return self._to_account(model)

    async def clear_active(self) -> None:
        async with self._sessionmaker() as session:
            await self._deactivate_all(session)
            await session.commit()

    async def get_active_account(self) -> Optional[ExchangeAccount]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(ExchangeAccountModel).where(ExchangeAccountModel.is_active.is_(True))
            )
            model = result.scalar_one_or_none()
            return self._to_account(model) if model else None

    async def get_credentials(self, account_id: str) -> Optional[ExchangeCredentials]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(ExchangeCredentialModel).where(ExchangeCredentialModel.account_id == account_id)
            )
            model = result.scalar_one_or_none()
            if not model:
                return None
            return ExchangeCredentials(
                account_id=account_id,
                api_key=self._cipher.decrypt(model.api_key_encrypted),
                api_secret=self._cipher.decrypt(model.api_secret_encrypted),
                passphrase=self._cipher.decrypt(model.passphrase_encrypted or "") or None,
                agent_key=self._cipher.decrypt(model.agent_key_encrypted or "") or None,
            )

    async def _deactivate_all(self, session: AsyncSession) -> None:
        await session.execute(update(ExchangeAccountModel).values(is_active=False))
        await session.flush()

    def _to_account(self, model: ExchangeAccountModel) -> ExchangeAccount:
        return ExchangeAccount(
            id=model.id,
            name=model.name,
            exchange=model.exchange,
            is_active=model.is_active,
            is_testnet=model.is_testnet,
            created_at=model.created_at,
            updated_at=model.updated_at,
            wallet_address=model.wallet_address,
            validation_status=model.validation_status,
            last_validated_at=model.last_validated_at,
            validation_error=model.validation_error,
        )
