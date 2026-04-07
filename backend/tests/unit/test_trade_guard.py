import pytest

from app.application.trade_guard.service import TradeGuardService
from app.domain.risk_management.models import DEFAULT_RISK_MANAGEMENT_CONFIG
from app.domain.llm_response_worker.models import ExecutionAction, ExecutionIdea
from app.domain.trade_guard.models import LeverageTier, PositionTierRange, TradeGuardConfig
from app.domain.trade_guard.rules import create_default_guard


def _base_config() -> TradeGuardConfig:
    return TradeGuardConfig(
        min_confidence=60.0,
        min_position_size=10.0,
        sl_min_roe=0.03,
        sl_max_roe=0.05,
        tp_min_roe=0.05,
        tp_max_roe=0.2,
        dust_threshold_usd=15.0,
        default_leverage=1,
        leverage_tiers=[LeverageTier(leverage=5, symbols=["BTC"])],
        position_tier_ranges=[
            PositionTierRange(tier=1, min_pct=0.70, max_pct=1.00),
            PositionTierRange(tier=2, min_pct=0.35, max_pct=0.70),
            PositionTierRange(tier=3, min_pct=0.15, max_pct=0.35),
        ],
    )


def test_max_leverage_modifier_caps_to_highest_tier():
    config = _base_config()
    config = TradeGuardConfig(
        min_confidence=config.min_confidence,
        min_position_size=config.min_position_size,
        sl_min_roe=config.sl_min_roe,
        sl_max_roe=config.sl_max_roe,
        tp_min_roe=config.tp_min_roe,
        tp_max_roe=config.tp_max_roe,
        dust_threshold_usd=config.dust_threshold_usd,
        default_leverage=config.default_leverage,
        leverage_tiers=[
            LeverageTier(leverage=3, symbols=["BTC"]),
            LeverageTier(leverage=5, symbols=["BTC"]),
        ],
        position_tier_ranges=config.position_tier_ranges,
    )

    guard = create_default_guard(config)
    decision = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG,
        symbol="BTC",
        leverage=10,
        confidence=70,
    )
    result = guard.validate(decision, account_state={"account_value": 1000}, portfolio_exposure_pct=25)
    assert result.is_valid is True
    assert result.decision.leverage == 5


def test_tier_position_size_uses_portfolio_exposure_pct():
    config = TradeGuardConfig(
        min_confidence=60.0,
        min_position_size=10.0,
        sl_min_roe=0.03,
        sl_max_roe=0.05,
        tp_min_roe=0.05,
        tp_max_roe=0.2,
        dust_threshold_usd=15.0,
        default_leverage=1,
        leverage_tiers=[LeverageTier(leverage=2, symbols=["ETH"])],
        position_tier_ranges=[
            PositionTierRange(tier=1, min_pct=0.70, max_pct=1.00),
            PositionTierRange(tier=2, min_pct=0.35, max_pct=0.70),
            PositionTierRange(tier=3, min_pct=0.15, max_pct=0.35),
        ],
    )
    guard = create_default_guard(config)
    decision = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG,
        symbol="ETH",
        leverage=2,
        tier=2,
        position_pct=0.5,
        confidence=70,
    )
    result = guard.validate(
        decision,
        account_state={"account_value": 1000},
        portfolio_exposure_pct=25,
    )
    assert result.is_valid is True
    assert result.decision.position_size_usd == 250.0


def test_update_sl_rejects_wider_stop_loss():
    config = _base_config()
    guard = create_default_guard(config)
    decision = ExecutionIdea(
        action=ExecutionAction.UPDATE_SL,
        symbol="BTC",
        stop_loss=100.0,
        new_stop_loss=90.0,
    )
    open_positions = [{"symbol": "BTC", "direction": "long", "size": 1}]
    result = guard.validate(decision, open_positions=open_positions)
    assert result.is_valid is True
    assert result.decision.action == ExecutionAction.HOLD


def test_update_sl_allows_tighter_stop_loss():
    config = _base_config()
    guard = create_default_guard(config)
    decision = ExecutionIdea(
        action=ExecutionAction.UPDATE_SL,
        symbol="BTC",
        stop_loss=100.0,
        new_stop_loss=110.0,
    )
    open_positions = [{"symbol": "BTC", "direction": "long", "size": 1}]
    result = guard.validate(decision, open_positions=open_positions)
    assert result.is_valid is True
    assert result.decision.action == ExecutionAction.UPDATE_SL


def test_update_sl_uses_open_orders_when_symbol_formats_differ():
    config = _base_config()
    guard = create_default_guard(config)
    decision = ExecutionIdea(
        action=ExecutionAction.UPDATE_SL,
        symbol="BTC",
        new_stop_loss=90.0,
    )
    open_positions = [{"symbol": "BTC/USDT:USDT", "direction": "long", "size": 1}]
    open_orders = [
        {
            "symbol": "BTC/USDT:USDT",
            "type": "STOP_MARKET",
            "stopPrice": 100.0,
            "status": "NEW",
        }
    ]
    result = guard.validate(decision, open_positions=open_positions, open_orders=open_orders)
    assert result.is_valid is True
    assert result.decision.action == ExecutionAction.HOLD


def test_update_sl_converts_stop_loss_roe_to_break_even_price_for_long():
    config = _base_config()
    guard = create_default_guard(config)
    decision = ExecutionIdea(
        action=ExecutionAction.UPDATE_SL,
        symbol="BTC",
        stop_loss_roe=0.0,
    )
    open_positions = [
        {
            "symbol": "BTC",
            "direction": "long",
            "size": 1,
            "entry_price": 100.0,
            "mark_price": 104.0,
            "leverage": 5,
        }
    ]

    result = guard.validate(decision, open_positions=open_positions)

    assert result.is_valid is True
    assert result.decision.action == ExecutionAction.UPDATE_SL
    assert result.decision.new_stop_loss == 100.0


def test_update_sl_converts_stop_loss_roe_to_locked_profit_for_short():
    config = _base_config()
    guard = create_default_guard(config)
    decision = ExecutionIdea(
        action=ExecutionAction.UPDATE_SL,
        symbol="BTC",
        stop_loss_roe=0.01,
    )
    open_positions = [
        {
            "symbol": "BTC",
            "direction": "short",
            "size": -1,
            "entry_price": 100.0,
            "mark_price": 97.0,
            "leverage": 5,
        }
    ]

    result = guard.validate(decision, open_positions=open_positions)

    assert result.is_valid is True
    assert result.decision.action == ExecutionAction.UPDATE_SL
    assert result.decision.new_stop_loss == 99.8


def test_update_sl_requires_position_context_for_stop_loss_roe():
    config = _base_config()
    guard = create_default_guard(config)
    decision = ExecutionIdea(
        action=ExecutionAction.UPDATE_SL,
        symbol="BTC",
        stop_loss_roe=0.0,
    )

    result = guard.validate(decision, open_positions=[])

    assert result.is_valid is False
    assert "requires an open position" in result.errors[0]


def test_update_tp_converts_take_profit_roe_to_price_for_long():
    config = _base_config()
    guard = create_default_guard(config)
    decision = ExecutionIdea(
        action=ExecutionAction.UPDATE_TP,
        symbol="BTC",
        take_profit_roe=0.02,
    )
    open_positions = [
        {
            "symbol": "BTC",
            "direction": "long",
            "size": 1,
            "entry_price": 100.0,
            "mark_price": 101.0,
            "leverage": 5,
        }
    ]

    result = guard.validate(decision, open_positions=open_positions)

    assert result.is_valid is True
    assert result.decision.action == ExecutionAction.UPDATE_TP
    assert result.decision.new_take_profit == 100.4


def test_update_tp_converts_take_profit_roe_to_price_for_short():
    config = _base_config()
    guard = create_default_guard(config)
    decision = ExecutionIdea(
        action=ExecutionAction.UPDATE_TP,
        symbol="BTC",
        take_profit_roe=0.015,
    )
    open_positions = [
        {
            "symbol": "BTC",
            "direction": "short",
            "size": -1,
            "entry_price": 100.0,
            "mark_price": 99.0,
            "leverage": 5,
        }
    ]

    result = guard.validate(decision, open_positions=open_positions)

    assert result.is_valid is True
    assert result.decision.action == ExecutionAction.UPDATE_TP
    assert result.decision.new_take_profit == 99.7


def test_update_tp_requires_position_context_for_take_profit_roe():
    config = _base_config()
    guard = create_default_guard(config)
    decision = ExecutionIdea(
        action=ExecutionAction.UPDATE_TP,
        symbol="BTC",
        take_profit_roe=0.01,
    )

    result = guard.validate(decision, open_positions=[])

    assert result.is_valid is False
    assert "requires an open position" in result.errors[0]


def test_update_tp_caps_extension_to_one_percent_roe_per_cycle():
    config = _base_config()
    guard = create_default_guard(config)
    decision = ExecutionIdea(
        action=ExecutionAction.UPDATE_TP,
        symbol="BTC",
        take_profit_roe=0.05,
    )
    open_positions = [
        {
            "symbol": "BTC",
            "direction": "long",
            "size": 1,
            "entry_price": 100.0,
            "mark_price": 101.0,
            "leverage": 5,
        }
    ]
    open_orders = [
        {
            "symbol": "BTC",
            "type": "TAKE_PROFIT_MARKET",
            "stopPrice": 100.4,
            "status": "NEW",
        }
    ]

    result = guard.validate(decision, open_positions=open_positions, open_orders=open_orders)

    assert result.is_valid is True
    assert result.decision.action == ExecutionAction.UPDATE_TP
    assert result.decision.new_take_profit == 100.6


def test_update_tp_within_one_percent_roe_delta_is_not_clamped():
    config = _base_config()
    guard = create_default_guard(config)
    decision = ExecutionIdea(
        action=ExecutionAction.UPDATE_TP,
        symbol="BTC",
        take_profit_roe=0.028,
    )
    open_positions = [
        {
            "symbol": "BTC",
            "direction": "long",
            "size": 1,
            "entry_price": 100.0,
            "mark_price": 101.0,
            "leverage": 5,
        }
    ]
    open_orders = [
        {
            "symbol": "BTC",
            "type": "TAKE_PROFIT_MARKET",
            "stopPrice": 100.4,
            "status": "NEW",
        }
    ]

    result = guard.validate(decision, open_positions=open_positions, open_orders=open_orders)

    assert result.is_valid is True
    assert result.decision.action == ExecutionAction.UPDATE_TP
    assert result.decision.new_take_profit == 100.56


def test_initial_stop_loss_honors_model_roe_when_in_bounds():
    config = _base_config()
    guard = create_default_guard(config)
    decision = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG,
        symbol="BTC",
        leverage=5,
        position_size_usd=100.0,
        confidence=70,
        stop_loss_roe=0.04,
    )

    result = guard.validate(
        decision,
        account_state={"account_value": 1000},
        portfolio_exposure_pct=25,
        price_fetcher=lambda _: 100.0,
    )

    assert result.is_valid is True
    assert result.decision.stop_loss == 99.2
    assert result.decision.stop_loss_roe == 0.04


def test_initial_stop_loss_clamps_model_roe_to_server_bounds():
    config = _base_config()
    guard = create_default_guard(config)
    decision = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG,
        symbol="BTC",
        leverage=5,
        position_size_usd=100.0,
        confidence=70,
        stop_loss_roe=0.10,
    )

    result = guard.validate(
        decision,
        account_state={"account_value": 1000},
        portfolio_exposure_pct=25,
        price_fetcher=lambda _: 100.0,
    )

    assert result.is_valid is True
    assert result.decision.stop_loss == 99.0
    assert result.decision.stop_loss_roe == 0.05


def test_initial_stop_loss_clamps_model_price_via_implied_roe():
    config = _base_config()
    guard = create_default_guard(config)
    decision = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG,
        symbol="BTC",
        leverage=5,
        position_size_usd=100.0,
        confidence=70,
        stop_loss=98.0,
    )

    result = guard.validate(
        decision,
        account_state={"account_value": 1000},
        portfolio_exposure_pct=25,
        price_fetcher=lambda _: 100.0,
    )

    assert result.is_valid is True
    assert result.decision.stop_loss == 99.0
    assert result.decision.stop_loss_roe == 0.05


def test_take_profit_honors_model_roe_when_in_bounds():
    config = TradeGuardConfig(
        min_confidence=60.0,
        min_position_size=10.0,
        sl_min_roe=0.03,
        sl_max_roe=0.05,
        tp_min_roe=0.08,
        tp_max_roe=0.2,
        dust_threshold_usd=15.0,
        default_leverage=1,
        leverage_tiers=[],
        position_tier_ranges=[],
    )
    guard = create_default_guard(config)
    decision = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG,
        symbol="BTC",
        leverage=1,
        position_size_usd=100.0,
        confidence=70,
        take_profit_roe=0.15,
    )

    result = guard.validate(
        decision,
        account_state={"account_value": 1000},
        portfolio_exposure_pct=25,
        price_fetcher=lambda _: 100.0,
    )

    assert result.is_valid is True
    assert result.decision.take_profit == 115.0
    assert result.decision.take_profit_roe == 0.15


def test_take_profit_clamps_model_roe_to_server_bounds():
    config = TradeGuardConfig(
        min_confidence=60.0,
        min_position_size=10.0,
        sl_min_roe=0.03,
        sl_max_roe=0.05,
        tp_min_roe=0.08,
        tp_max_roe=0.2,
        dust_threshold_usd=15.0,
        default_leverage=1,
        leverage_tiers=[],
        position_tier_ranges=[],
    )
    guard = create_default_guard(config)
    decision = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG,
        symbol="BTC",
        leverage=1,
        position_size_usd=100.0,
        confidence=70,
        take_profit_roe=0.5,
    )

    result = guard.validate(
        decision,
        account_state={"account_value": 1000},
        portfolio_exposure_pct=25,
        price_fetcher=lambda _: 100.0,
    )

    assert result.is_valid is True
    assert result.decision.take_profit == 120.0
    assert result.decision.take_profit_roe == 0.2


def test_limit_entry_uses_limit_price_as_reference_for_model_price_levels():
    config = TradeGuardConfig(
        min_confidence=60.0,
        min_position_size=10.0,
        sl_min_roe=0.03,
        sl_max_roe=0.05,
        tp_min_roe=0.05,
        tp_max_roe=0.2,
        dust_threshold_usd=15.0,
        default_leverage=5,
        leverage_tiers=[],
        position_tier_ranges=[],
    )
    guard = create_default_guard(config)
    decision = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG_LIMIT,
        symbol="BTC",
        leverage=5,
        position_size_usd=100.0,
        limit_price=100.0,
        confidence=70,
        stop_loss=99.0,
        take_profit=104.0,
    )

    result = guard.validate(
        decision,
        account_state={"account_value": 1000},
        portfolio_exposure_pct=25,
        price_fetcher=lambda _: 110.0,
    )

    assert result.is_valid is True
    assert result.decision.stop_loss == 99.0
    assert result.decision.stop_loss_roe == 0.05
    assert result.decision.take_profit == 104.0
    assert result.decision.take_profit_roe == 0.2


def test_limit_entry_honors_model_initial_protection_when_in_bounds():
    config = TradeGuardConfig(
        min_confidence=60.0,
        min_position_size=10.0,
        sl_min_roe=0.03,
        sl_max_roe=0.05,
        tp_min_roe=0.08,
        tp_max_roe=0.2,
        dust_threshold_usd=15.0,
        default_leverage=5,
        leverage_tiers=[],
        position_tier_ranges=[],
    )
    guard = create_default_guard(config)
    decision = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG_LIMIT,
        symbol="BTC",
        leverage=5,
        position_size_usd=100.0,
        limit_price=100.0,
        confidence=70,
        stop_loss_roe=0.04,
        take_profit_roe=0.18,
    )

    result = guard.validate(
        decision,
        account_state={"account_value": 1000},
        portfolio_exposure_pct=25,
        price_fetcher=lambda _: 100.0,
    )

    assert result.is_valid is True
    assert result.decision.stop_loss == 99.2
    assert result.decision.stop_loss_roe == 0.04
    assert result.decision.take_profit == 103.6
    assert result.decision.take_profit_roe == 0.18


def test_initial_take_profit_price_is_honored_even_when_tp_default_is_disabled():
    config = TradeGuardConfig(
        min_confidence=60.0,
        min_position_size=10.0,
        sl_min_roe=0.03,
        sl_max_roe=0.05,
        tp_min_roe=0.0,
        tp_max_roe=0.2,
        dust_threshold_usd=15.0,
        default_leverage=1,
        leverage_tiers=[],
        position_tier_ranges=[],
    )
    guard = create_default_guard(config)
    decision = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG,
        symbol="BTC",
        leverage=1,
        position_size_usd=100.0,
        confidence=70,
        take_profit=112.0,
    )

    result = guard.validate(
        decision,
        account_state={"account_value": 1000},
        portfolio_exposure_pct=25,
        price_fetcher=lambda _: 100.0,
    )

    assert result.is_valid is True
    assert result.decision.take_profit == 112.0
    assert result.decision.take_profit_roe == 0.12


def test_initial_entry_falls_back_to_server_defaults_when_model_omits_roe():
    config = _base_config()
    guard = create_default_guard(config)
    decision = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG,
        symbol="BTC",
        leverage=5,
        position_size_usd=100.0,
        confidence=70,
    )

    result = guard.validate(
        decision,
        account_state={"account_value": 1000},
        portfolio_exposure_pct=25,
        price_fetcher=lambda _: 100.0,
    )

    assert result.is_valid is True
    assert result.decision.stop_loss == 99.4
    assert result.decision.stop_loss_roe == 0.03
    assert result.decision.take_profit == 101.0
    assert result.decision.take_profit_roe == 0.05


def test_initial_take_profit_is_disabled_when_ui_tp_min_is_zero():
    config = TradeGuardConfig(
        min_confidence=60.0,
        min_position_size=10.0,
        sl_min_roe=0.03,
        sl_max_roe=0.05,
        tp_min_roe=0.0,
        tp_max_roe=0.2,
        dust_threshold_usd=15.0,
        default_leverage=1,
        leverage_tiers=[],
        position_tier_ranges=[],
    )
    guard = create_default_guard(config)
    decision = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG,
        symbol="BTC",
        leverage=1,
        position_size_usd=100.0,
        confidence=70,
    )

    result = guard.validate(
        decision,
        account_state={"account_value": 1000},
        portfolio_exposure_pct=25,
        price_fetcher=lambda _: 100.0,
    )

    assert result.is_valid is True
    assert result.decision.take_profit is None
    assert result.decision.take_profit_roe is None


class _InMemoryTradeGuardConfigRepository:
    def __init__(self) -> None:
        self.config: TradeGuardConfig | None = None

    async def get_config(self) -> TradeGuardConfig | None:
        return self.config

    async def upsert(self, config: TradeGuardConfig) -> TradeGuardConfig:
        self.config = config
        return config


class _StubRiskConfigService:
    async def get_config(self):
        return DEFAULT_RISK_MANAGEMENT_CONFIG


@pytest.mark.asyncio
async def test_trade_guard_service_preserves_zero_tp_min_roe():
    repository = _InMemoryTradeGuardConfigRepository()
    service = TradeGuardService(repository, _StubRiskConfigService())

    config = TradeGuardConfig(
        min_confidence=60.0,
        min_position_size=10.0,
        sl_min_roe=0.03,
        sl_max_roe=0.05,
        tp_min_roe=0.0,
        tp_max_roe=0.2,
        dust_threshold_usd=15.0,
        default_leverage=1,
        leverage_tiers=[],
        position_tier_ranges=[],
    )

    updated = await service.update_config(config)
    reloaded = await service.get_config()

    assert updated.tp_min_roe == 0.0
    assert reloaded.tp_min_roe == 0.0


def test_limit_entry_rejected_when_pending_entry_exists_for_symbol():
    config = _base_config()
    guard = create_default_guard(config)
    decision = ExecutionIdea(
        action=ExecutionAction.OPEN_LONG_LIMIT,
        symbol="BTC",
        limit_price=100.0,
        confidence=80,
    )

    result = guard.validate(
        decision,
        open_positions=[],
        pending_entries=[{"symbol": "BTC", "status": "RESTING"}],
    )

    assert result.is_valid is False
    assert "Active pending limit entry already exists" in result.errors[0]


def test_limit_entry_rejected_when_symbol_is_not_flat():
    config = _base_config()
    guard = create_default_guard(config)
    decision = ExecutionIdea(
        action=ExecutionAction.OPEN_SHORT_LIMIT,
        symbol="BTC",
        limit_price=100.0,
        confidence=80,
    )

    result = guard.validate(
        decision,
        open_positions=[{"symbol": "BTC/USDT:USDT", "direction": "long", "size": 1}],
    )

    assert result.is_valid is False
    assert "only allowed when flat" in result.errors[0]
