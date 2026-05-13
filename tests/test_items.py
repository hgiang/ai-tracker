from datetime import datetime, timezone

import pytest

from app.models.item import ContentType, Item
from app.models.source import Source


@pytest.fixture
async def seeded_db(db_session):
    source = Source(
        name="Test Source", slug="test", adapter_type="hackernews", url="https://example.com"
    )
    db_session.add(source)
    await db_session.flush()

    for i in range(3):
        db_session.add(
            Item(
                source_id=source.id,
                source_item_id=f"item-{i}",
                url=f"https://example.com/{i}",
                canonical_url=f"https://example.com/{i}",
                title=f"Test Item {i}",
                normalized_title=f"test item {i}",
                content_type=ContentType.NEWS,
                fetched_at=datetime.now(timezone.utc),
                relevance_score=0.5 - (i * 0.1),
            )
        )
    await db_session.commit()
    return db_session


@pytest.mark.asyncio
async def test_list_items(client, seeded_db):
    resp = await client.get("/api/items")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3


@pytest.mark.asyncio
async def test_list_items_pagination(client, seeded_db):
    resp = await client.get("/api/items?page=1&limit=2")
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] == 3


@pytest.mark.asyncio
async def test_get_item(client, seeded_db):
    resp = await client.get("/api/items/1")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Test Item 0"


@pytest.mark.asyncio
async def test_get_item_not_found(client, seeded_db):
    resp = await client.get("/api/items/999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_set_feedback_up(client, seeded_db):
    resp = await client.post("/api/items/1/feedback", json={"feedback": "up"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_feedback"] == "up"
    assert data["feedback_at"] is not None


@pytest.mark.asyncio
async def test_set_feedback_down(client, seeded_db):
    resp = await client.post("/api/items/2/feedback", json={"feedback": "down"})
    assert resp.status_code == 200
    assert resp.json()["user_feedback"] == "down"


@pytest.mark.asyncio
async def test_clear_feedback(client, seeded_db):
    await client.post("/api/items/1/feedback", json={"feedback": "up"})
    resp = await client.post("/api/items/1/feedback", json={"feedback": None})
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_feedback"] is None
    assert data["feedback_at"] is None


@pytest.mark.asyncio
async def test_invalid_feedback_value(client, seeded_db):
    resp = await client.post("/api/items/1/feedback", json={"feedback": "meh"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_feedback_item_not_found(client, seeded_db):
    resp = await client.post("/api/items/999/feedback", json={"feedback": "up"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_filter_items_by_feedback(client, seeded_db):
    await client.post("/api/items/1/feedback", json={"feedback": "up"})
    await client.post("/api/items/2/feedback", json={"feedback": "down"})

    up_resp = await client.get("/api/items?feedback=up")
    assert up_resp.json()["total"] == 1
    assert up_resp.json()["items"][0]["id"] == 1

    down_resp = await client.get("/api/items?feedback=down")
    assert down_resp.json()["total"] == 1
    assert down_resp.json()["items"][0]["id"] == 2
