import pytest

from app.infrastructure.external.nofxos_dynamic_assets import NofXOSDynamicAssetsClient


@pytest.mark.asyncio
async def test_fetch_multi_source_assets_supports_netflow_sources(monkeypatch):
    client = NofXOSDynamicAssetsClient(base_url="https://example.test")
    calls: list[tuple[str, dict]] = []

    async def fake_get_json(http_client, url, params):
        calls.append((url, dict(params)))
        if url.endswith("/netflow/top-ranking"):
            return {
                "data": {
                    "netflows": [
                        {"symbol": "BTCUSDT", "rank": 2},
                        {"symbol": "ETHUSDT", "rank": 1},
                    ]
                }
            }
        if url.endswith("/netflow/low-ranking"):
            return {
                "data": {
                    "netflows": [
                        {"symbol": "XRPUSDT"},
                        {"symbol": "ETHUSDT"},
                    ]
                }
            }
        if url.endswith("/heatmap/list"):
            return {
                "success": True,
                "data": {
                    "heatmaps": [
                        {"symbol": "SOL", "rank": 2},
                        {"symbol": "BTC", "rank": 1},
                    ]
                },
            }
        return {}

    monkeypatch.setattr(client, "_get_json", fake_get_json)

    assets = await client.fetch_multi_source_assets(
        {
            "netflow_top": {"enabled": True, "limit": 40, "duration": "1h"},
            "netflow_low": {"enabled": True, "limit": 40, "duration": "1h"},
            "futures_depth": {"enabled": True, "limit": 60},
        },
        api_key="cm_demo",
    )

    assert assets == ["ETH", "BTC", "XRP", "SOL"]
    assert len(calls) == 3

    top_params = next(params for url, params in calls if url.endswith("/netflow/top-ranking"))
    low_params = next(params for url, params in calls if url.endswith("/netflow/low-ranking"))
    depth_params = next(params for url, params in calls if url.endswith("/heatmap/list"))

    assert top_params["auth"] == "cm_demo"
    assert top_params["limit"] == 40
    assert top_params["duration"] == "1h"
    assert top_params["type"] == "institution"
    assert top_params["trade"] == "future"

    assert low_params["auth"] == "cm_demo"
    assert low_params["limit"] == 40
    assert low_params["duration"] == "1h"
    assert low_params["type"] == "institution"
    assert low_params["trade"] == "future"

    assert depth_params["auth"] == "cm_demo"
    assert depth_params["limit"] == 60
    assert depth_params["trade"] == "future"
