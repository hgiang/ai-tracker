import pytest


@pytest.mark.asyncio
async def test_health_check(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_frontend_serves_index(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "AI Tracker" in resp.text
