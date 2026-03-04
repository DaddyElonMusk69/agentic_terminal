import logging

import httpx

from app.infrastructure.external.nofxos_client import NofXOSClient


def test_timeout_uses_constructor_override():
    client = NofXOSClient(api_key="demo", timeout=7)
    assert client._timeout == 7.0


def test_timeout_uses_environment_value(monkeypatch):
    monkeypatch.setenv("NOFXOS_TIMEOUT_SECONDS", "18.5")
    client = NofXOSClient(api_key="demo", timeout=None)
    assert client._timeout == 18.5


def test_timeout_invalid_environment_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("NOFXOS_TIMEOUT_SECONDS", "not-a-number")
    client = NofXOSClient(api_key="demo", timeout=None)
    assert client._timeout == float(NofXOSClient.DEFAULT_TIMEOUT)


def test_network_error_log_includes_exception_type(monkeypatch, caplog):
    client = NofXOSClient(api_key="demo", timeout=1)
    monkeypatch.setattr(client, "_retry_count", 0)
    monkeypatch.setattr(client, "_throttle", lambda: None)

    def _raise_read_timeout(url, params):
        raise httpx.ReadTimeout("", request=httpx.Request("GET", url))

    monkeypatch.setattr(client._client, "get", _raise_read_timeout)
    caplog.set_level(logging.WARNING)

    result = client.get_coin_data("NEAR")

    assert result is None
    assert "NofXOS API network error" in caplog.text
    assert "error_type=ReadTimeout" in caplog.text
