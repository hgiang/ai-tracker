from datetime import date, datetime, timezone

import pytest

from app.models.item import ContentType, Item
from app.models.source import Source
from app.services.digest import generate_digest


@pytest.fixture
async def db_with_items(db_session):
    source = Source(
        name="Test", slug="test", adapter_type="hackernews", url="https://example.com"
    )
    db_session.add(source)
    await db_session.flush()

    db_session.add(
        Item(
            source_id=source.id,
            source_item_id="d1",
            url="https://example.com/1",
            canonical_url="https://example.com/1",
            title="Top AI News",
            normalized_title="top ai news",
            content_type=ContentType.NEWS,
            fetched_at=datetime.now(timezone.utc),
            relevance_score=0.9,
        )
    )
    await db_session.commit()
    return db_session


@pytest.mark.asyncio
async def test_generate_digest(db_with_items):
    digest = await generate_digest(db_with_items, target_date=date.today())
    assert digest.item_count == 1
    assert "Top AI News" in digest.content


@pytest.mark.asyncio
async def test_generate_digest_empty(db_session):
    digest = await generate_digest(db_session, target_date=date(2020, 1, 1))
    assert digest.item_count == 0
    assert "No items" in digest.content
