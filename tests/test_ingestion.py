from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.adapters.base import BaseAdapter
from app.models.item import ContentType, Item
from app.models.source import Source, SourceCheckpoint
from app.schemas.item import NormalizedItem
from app.services import ingestion


class FakeAdapter(BaseAdapter):
    def __init__(self, items):
        super().__init__("https://example.com")
        self._items = items

    async def fetch(self, checkpoint: str | None = None):
        return self._items, "next-checkpoint"


@pytest.mark.asyncio
async def test_sync_source_batches_duplicate_checks(db_session, monkeypatch):
    source = Source(
        name="X Source",
        slug="x-test",
        adapter_type="x",
        url="https://x.com",
    )
    db_session.add(source)
    await db_session.flush()

    db_session.add(
        Item(
            source_id=source.id,
            source_item_id="existing",
            url="https://x.com/alice/status/1",
            canonical_url="https://x.com/alice/status/1",
            title="Existing post",
            normalized_title="existing post",
            content_type=ContentType.NEWS,
            fetched_at=datetime.now(timezone.utc),
            relevance_score=0.5,
        )
    )
    await db_session.commit()

    items = [
        NormalizedItem(
            source_item_id="existing",
            url="https://x.com/alice/status/1",
            title="Existing post",
            content_type=ContentType.NEWS,
        ),
        NormalizedItem(
            source_item_id="fresh-1",
            url="https://example.com/post?utm_source=twitter",
            title="Fresh post",
            content_type=ContentType.NEWS,
        ),
        NormalizedItem(
            source_item_id="fresh-2",
            url="https://example.com/post",
            title="Fresh post!!!",
            content_type=ContentType.NEWS,
        ),
    ]

    monkeypatch.setattr(ingestion, "get_adapter", lambda *args, **kwargs: FakeAdapter(items))

    result = await ingestion.sync_source(db_session, source)

    total_items = await db_session.scalar(select(func.count(Item.id)))
    checkpoint = await db_session.scalar(
        select(SourceCheckpoint.checkpoint_value).where(SourceCheckpoint.source_id == source.id)
    )

    assert result.fetched == 3
    assert result.new == 1
    assert result.duplicates == 2
    assert total_items == 2
    assert checkpoint == "next-checkpoint"
