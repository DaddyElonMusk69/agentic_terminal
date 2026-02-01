import pytest


@pytest.mark.asyncio
async def test_health_ok(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "service" in payload
    assert "version" in payload
    assert "time" in payload


@pytest.mark.asyncio
async def test_health_ready_ok(client):
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload.get("checks")
