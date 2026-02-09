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
