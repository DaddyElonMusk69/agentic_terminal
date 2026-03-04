import pytest


class StubEmaStateManagerService:
    def __init__(self) -> None:
        self.cleared = False

    def clear_all_states(self) -> None:
        self.cleared = True

    async def get_config(self):
        return object()

    def get_all_states(self):
        if self.cleared:
            return {}
        return {"BTC/USDT": object()}


@pytest.mark.asyncio
async def test_clear_vegas_state_endpoint(client, monkeypatch):
    service = StubEmaStateManagerService()
    emitted: dict = {}

    async def fake_emit_state(_request, payload):
        emitted["payload"] = payload

    monkeypatch.setattr(
        "app.api.v1.ema_scanner.get_ema_state_manager_service",
        lambda: service,
    )
    monkeypatch.setattr(
        "app.api.v1.ema_scanner.build_vegas_state_payload",
        lambda states, _config: {"states": [{"ticker": "BTC/USDT"}]} if states else {"states": []},
    )
    monkeypatch.setattr("app.api.v1.ema_scanner._emit_state", fake_emit_state)

    response = await client.post("/api/v1/scanner/ema/state/clear")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["states"] == []
    assert service.cleared is True
    assert emitted.get("payload") == {"states": []}
