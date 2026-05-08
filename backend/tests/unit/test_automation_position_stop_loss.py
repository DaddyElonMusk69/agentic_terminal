from app.api.v1.automation import _extract_sl_tp


def test_automation_positions_ignore_add_tranche_stop_market_as_stop_loss():
    orders = [
        {
            "symbol": "BTC/USDT:USDT",
            "type": "STOP_MARKET",
            "stopPrice": 105.0,
            "closePosition": False,
            "status": "NEW",
        },
        {
            "symbol": "BTC/USDT:USDT",
            "type": "STOP_MARKET",
            "stopPrice": 100.0,
            "closePosition": True,
            "status": "NEW",
        },
    ]

    stop_loss, take_profit = _extract_sl_tp(orders)

    assert stop_loss == 100.0
    assert take_profit is None


def test_automation_positions_read_nested_close_position_stop_loss_flag():
    orders = [
        {
            "symbol": "ACHUSDT",
            "status": "NEW",
            "info": {
                "symbol": "ACHUSDT",
                "orderType": "STOP_MARKET",
                "triggerPrice": "0.005915",
                "closePosition": "true",
            },
        },
    ]

    stop_loss, take_profit = _extract_sl_tp(orders)

    assert stop_loss == 0.005915
    assert take_profit is None
