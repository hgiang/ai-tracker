from datetime import datetime, timedelta, timezone

import pytest

from app.models.item import ContentType, Item
from app.models.source import Source
from app.services.retention import cleanup_expired


@pytest.fixture
async def db_with_old_items(db_session):
    source = Source(
        name="Test", slug="test", adapter_type="hackernews", url="https://example.com"
    )
    db_session.add(source)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    old = now - timedelta(days=200)

    for i, fetched in enumerate([now, old]):
        db_session.add(
            Item(
                source_id=source.id,
                source_item_id=f"r{i}",
                url=f"https://example.com/r{i}",
                canonical_url=f"https://example.com/r{i}",
                title=f"Item {i}",
                normalized_title=f"item {i}",
                content_type=ContentType.NEWS,
                fetched_at=fetched,
                relevance_score=0.5,
            )
        )
    await db_session.commit()
    return db_session


@pytest.mark.asyncio
async def test_cleanup_expired(db_with_old_items):
    deleted = await cleanup_expired(db_with_old_items)
    assert deleted == 1
