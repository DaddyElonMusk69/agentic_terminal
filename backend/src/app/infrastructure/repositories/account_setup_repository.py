from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.portfolio.interfaces import AccountSetupRepository
from app.domain.portfolio.models import AccountSetup
from app.infrastructure.db.models.account_setup import AccountSetupModel


class SqlAccountSetupRepository(AccountSetupRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get_setup(self) -> Optional[AccountSetup]:
        async with self._sessionmaker() as session:
            result = await session.execute(select(AccountSetupModel).order_by(AccountSetupModel.id))
            model = result.scalars().first()
            if model is None:
                return None
            return AccountSetup(portfolio_exposure_pct=model.portfolio_exposure_pct)

    async def set_setup(self, setup: AccountSetup) -> AccountSetup:
        async with self._sessionmaker() as session:
            result = await session.execute(select(AccountSetupModel).order_by(AccountSetupModel.id))
            model = result.scalars().first()
            if model is None:
                model = AccountSetupModel(portfolio_exposure_pct=setup.portfolio_exposure_pct)
                session.add(model)
            else:
                model.portfolio_exposure_pct = setup.portfolio_exposure_pct
            await session.commit()
            return AccountSetup(portfolio_exposure_pct=model.portfolio_exposure_pct)
