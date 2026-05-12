from datetime import datetime, timezone

import pytest

from app.agent.tools import search_items
from app.models.item import ContentType, Item
from app.models.source import Source


@pytest.fixture
async def seeded_db(db_session):
    source = Source(
        name="Test Source", slug="test", adapter_type="hackernews", url="https://example.com"
    )
    db_session.add(source)
    await db_session.flush()

    db_session.add_all(
        [
            Item(
                source_id=source.id,
                source_item_id="a",
                url="https://example.com/a",
                canonical_url="https://example.com/a",
                title="Transformers paper",
                normalized_title="transformers paper",
                summary="Attention is all you need",
                content_type=ContentType.PAPER,
                fetched_at=datetime.now(timezone.utc),
                relevance_score=0.9,
            ),
            Item(
                source_id=source.id,
                source_item_id="b",
                url="https://example.com/b",
                canonical_url="https://example.com/b",
                title="Cooking recipes",
                normalized_title="cooking recipes",
                summary="Pasta tips",
                content_type=ContentType.NEWS,
                fetched_at=datetime.now(timezone.utc),
                relevance_score=0.1,
            ),
        ]
    )
    await db_session.commit()
    return db_session


@pytest.mark.asyncio
async def test_search_items_query_match(seeded_db):
    result = await search_items(seeded_db, query="transformers")
    assert result.total == 1
    assert result.items[0].title == "Transformers paper"


@pytest.mark.asyncio
async def test_search_items_filter_content_type(seeded_db):
    result = await search_items(seeded_db, content_type=ContentType.PAPER)
    assert result.total == 1
    assert result.items[0].content_type == ContentType.PAPER


@pytest.mark.asyncio
async def test_search_items_min_score(seeded_db):
    result = await search_items(seeded_db, min_score=0.5)
    assert result.total == 1
    assert result.items[0].relevance_score >= 0.5


@pytest.mark.asyncio
async def test_search_items_no_filters_returns_all(seeded_db):
    result = await search_items(seeded_db)
    assert result.total == 2
    assert result.items[0].relevance_score >= result.items[1].relevance_score


@pytest.mark.asyncio
async def test_search_items_invalid_limit(seeded_db):
    with pytest.raises(ValueError):
        await search_items(seeded_db, limit=0)
