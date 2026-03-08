from app.application.dynamic_assets.service import _normalize_sources, _strip_ai_sources_if_custom


def test_normalize_sources_includes_netflow_defaults():
    normalized = _normalize_sources({})
    assert "netflow_top" in normalized
    assert "netflow_low" in normalized
    assert normalized["netflow_top"]["enabled"] is False
    assert normalized["netflow_top"]["limit"] == 20
    assert normalized["netflow_top"]["duration"] == "1h"
    assert normalized["netflow_low"]["enabled"] is False
    assert normalized["netflow_low"]["limit"] == 20
    assert normalized["netflow_low"]["duration"] == "1h"


def test_custom_source_disables_nofx_only_sources():
    stripped = _strip_ai_sources_if_custom(
        {
            "ai500": {"enabled": True, "limit": 10},
            "ai300": {"enabled": True, "limit": 20, "level": ""},
            "oi_top": {"enabled": True, "limit": 20, "duration": "1h"},
            "oi_low": {"enabled": True, "limit": 20, "duration": "1h"},
            "netflow_top": {"enabled": True, "limit": 20, "duration": "1h"},
            "netflow_low": {"enabled": True, "limit": 20, "duration": "1h"},
        },
        "custom",
    )

    assert stripped["ai500"]["enabled"] is False
    assert stripped["ai300"]["enabled"] is False
    assert stripped["netflow_top"]["enabled"] is False
    assert stripped["netflow_low"]["enabled"] is False
    assert stripped["oi_top"]["enabled"] is True
    assert stripped["oi_low"]["enabled"] is True
