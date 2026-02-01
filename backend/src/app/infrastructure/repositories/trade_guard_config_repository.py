from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.trade_guard.interfaces import TradeGuardConfigRepository
from app.domain.trade_guard.models import LeverageTier, PositionTierRange, TradeGuardConfig
from app.infrastructure.db.models.trade_guard import TradeGuardConfigModel


class SqlTradeGuardConfigRepository(TradeGuardConfigRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get_config(self) -> Optional[TradeGuardConfig]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(TradeGuardConfigModel)
                .order_by(TradeGuardConfigModel.id.desc())
                .limit(1)
            )
            model = result.scalars().first()
            if model is None:
                return None
            return _to_config(model)

    async def upsert(self, config: TradeGuardConfig) -> TradeGuardConfig:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(TradeGuardConfigModel)
                .order_by(TradeGuardConfigModel.id.desc())
                .limit(1)
            )
            model = result.scalars().first()
            if model is None:
                model = TradeGuardConfigModel()
                session.add(model)

            model.min_confidence = config.min_confidence
            model.min_position_size = config.min_position_size
            model.sl_min_roe = config.sl_min_roe
            model.sl_max_roe = config.sl_max_roe
            model.tp_min_roe = config.tp_min_roe
            model.tp_max_roe = config.tp_max_roe
            model.dust_threshold_usd = config.dust_threshold_usd
            model.default_leverage = int(config.default_leverage)
            model.leverage_tiers = _serialize_leverage_tiers(config.leverage_tiers)
            model.position_tier_ranges = _serialize_position_tier_ranges(config.position_tier_ranges)

            await session.commit()
            await session.refresh(model)
            return _to_config(model)


def _parse_leverage_tiers(payload: List[dict]) -> List[LeverageTier]:
    tiers: List[LeverageTier] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        leverage = item.get("leverage")
        symbols = item.get("symbols")
        if leverage is None or not isinstance(symbols, list):
            continue
        tiers.append(
            LeverageTier(
                leverage=int(leverage),
                symbols=[str(symbol).upper() for symbol in symbols],
            )
        )
    return tiers


def _parse_position_tier_ranges(payload: List[dict]) -> List[PositionTierRange]:
    tiers: List[PositionTierRange] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        tier = item.get("tier")
        min_pct = item.get("min_pct")
        max_pct = item.get("max_pct")
        if tier is None or min_pct is None or max_pct is None:
            continue
        try:
            tier_value = int(tier)
            min_value = float(min_pct)
            max_value = float(max_pct)
        except (TypeError, ValueError):
            continue
        tiers.append(PositionTierRange(tier=tier_value, min_pct=min_value, max_pct=max_value))
    return tiers


def _serialize_leverage_tiers(tiers: List[LeverageTier]) -> List[dict]:
    payload: List[dict] = []
    for tier in tiers:
        payload.append(
            {
                "leverage": int(tier.leverage),
                "symbols": [symbol.upper() for symbol in tier.symbols],
            }
        )
    return payload


def _serialize_position_tier_ranges(tiers: List[PositionTierRange]) -> List[dict]:
    payload: List[dict] = []
    for tier in tiers:
        payload.append(
            {
                "tier": int(tier.tier),
                "min_pct": float(tier.min_pct),
                "max_pct": float(tier.max_pct),
            }
        )
    return payload


def _to_config(model: TradeGuardConfigModel) -> TradeGuardConfig:
    leverage_tiers = _parse_leverage_tiers(model.leverage_tiers or [])
    position_tier_ranges = _parse_position_tier_ranges(model.position_tier_ranges or [])
    return TradeGuardConfig(
        min_confidence=model.min_confidence,
        min_position_size=model.min_position_size,
        sl_min_roe=model.sl_min_roe,
        sl_max_roe=model.sl_max_roe,
        tp_min_roe=model.tp_min_roe,
        tp_max_roe=model.tp_max_roe,
        dust_threshold_usd=model.dust_threshold_usd,
        default_leverage=int(model.default_leverage) if model.default_leverage is not None else 1,
        leverage_tiers=leverage_tiers,
        position_tier_ranges=position_tier_ranges,
    )
