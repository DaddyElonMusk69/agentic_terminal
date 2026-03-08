from app.application.dynamic_assets.service import (
    _filter_excluded_assets,
    _normalize_sources,
    _strip_ai_sources_if_custom,
)


def test_normalize_sources_includes_netflow_and_depth_defaults():
    normalized = _normalize_sources({})
    assert "netflow_top" in normalized
    assert "netflow_low" in normalized
    assert normalized["netflow_top"]["enabled"] is False
    assert normalized["netflow_top"]["limit"] == 20
    assert normalized["netflow_top"]["duration"] == "1h"
    assert normalized["netflow_low"]["enabled"] is False
    assert normalized["netflow_low"]["limit"] == 20
    assert normalized["netflow_low"]["duration"] == "1h"
    assert "futures_depth" in normalized
    assert normalized["futures_depth"]["enabled"] is False
    assert normalized["futures_depth"]["limit"] == 60
    assert "excluded_assets" in normalized
    assert normalized["excluded_assets"]["enabled"] is False
    assert normalized["excluded_assets"]["symbols"] == ""


def test_custom_source_disables_nofx_only_sources():
    stripped = _strip_ai_sources_if_custom(
        {
            "ai500": {"enabled": True, "limit": 10},
            "ai300": {"enabled": True, "limit": 20, "level": ""},
            "oi_top": {"enabled": True, "limit": 20, "duration": "1h"},
            "oi_low": {"enabled": True, "limit": 20, "duration": "1h"},
            "netflow_top": {"enabled": True, "limit": 20, "duration": "1h"},
            "netflow_low": {"enabled": True, "limit": 20, "duration": "1h"},
            "futures_depth": {"enabled": True, "limit": 60},
            "excluded_assets": {"enabled": True, "symbols": "BTC, ETH"},
        },
        "custom",
    )

    assert stripped["ai500"]["enabled"] is False
    assert stripped["ai300"]["enabled"] is False
    assert stripped["netflow_top"]["enabled"] is False
    assert stripped["netflow_low"]["enabled"] is False
    assert stripped["futures_depth"]["enabled"] is False
    assert stripped["excluded_assets"]["enabled"] is True
    assert stripped["oi_top"]["enabled"] is True
    assert stripped["oi_low"]["enabled"] is True


def test_filter_excluded_assets_removes_configured_symbols_before_normalization():
    assets = ["BTCUSDT", "ETH", "SOLUSDT", "DOGE"]
    sources = {"excluded_assets": {"enabled": False, "symbols": "BTC, sol"}}

    filtered = _filter_excluded_assets(assets, sources)

    assert filtered == ["ETH", "DOGE"]
