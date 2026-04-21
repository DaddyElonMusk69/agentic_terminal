from app.api.v1.agent_templates import (
    PromptPreviewRequest,
    _build_chart_requests,
    _select_available_quant_intervals,
)


def test_build_chart_requests_keeps_extra_configured_intervals():
    payload = PromptPreviewRequest(ticker="BTC")

    requests = _build_chart_requests(
        chart_defaults={"vegas_interval_configs": {"2h": 60, "30m": 40, "12h": 80}},
        payload=payload,
        monitored_intervals=["2h", "4h", "12h"],
    )

    assert [item.interval for item in requests] == ["30m", "2h", "12h"]
    assert [item.candles for item in requests] == [40, 60, 80]


class _StubQuantService:
    def __init__(self, available: set[tuple[str, str]]) -> None:
        self._available = available

    def get_snapshot(self, ticker: str, interval: str):
        if (ticker, interval) in self._available:
            return {"ticker": ticker, "interval": interval}
        return None


def test_select_available_quant_intervals_allows_chart_only_intervals():
    quant_service = _StubQuantService({("BTC", "30m"), ("BTC", "2h")})

    available, missing = _select_available_quant_intervals(
        "BTC",
        ["5m", "30m", "2h"],
        quant_service,
    )

    assert available == ["30m", "2h"]
    assert missing == ["BTC@5m"]
