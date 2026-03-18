from app.api.v1.agent_templates import PromptPreviewRequest, _build_chart_requests


def test_build_chart_requests_keeps_extra_configured_intervals():
    payload = PromptPreviewRequest(ticker="BTC")

    requests = _build_chart_requests(
        chart_defaults={"vegas_interval_configs": {"2h": 60, "30m": 40, "12h": 80}},
        payload=payload,
        monitored_intervals=["2h", "4h", "12h"],
    )

    assert [item.interval for item in requests] == ["30m", "2h", "12h"]
    assert [item.candles for item in requests] == [40, 60, 80]
