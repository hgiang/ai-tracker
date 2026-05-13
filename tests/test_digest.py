import json
from datetime import date, datetime, timezone

import pytest

from app.models.item import ContentType, Item
from app.models.source import Source
from app.services import digest as digest_mod
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


@pytest.fixture
async def db_with_mixed_items(db_session):
    source = Source(
        name="Mixed", slug="mixed", adapter_type="hackernews", url="https://example.com"
    )
    db_session.add(source)
    await db_session.flush()
    for i, title in enumerate(["Keep me LLM", "Drop me crypto", "Keep me agentic"], start=1):
        db_session.add(
            Item(
                source_id=source.id,
                source_item_id=f"m{i}",
                url=f"https://example.com/{i}",
                canonical_url=f"https://example.com/{i}",
                title=title,
                normalized_title=title.lower(),
                content_type=ContentType.NEWS,
                fetched_at=datetime.now(timezone.utc),
                relevance_score=0.9 - i * 0.01,
            )
        )
    await db_session.commit()
    return db_session


@pytest.mark.asyncio
async def test_digest_skips_rerank_when_provider_unset(db_with_mixed_items, monkeypatch):
    monkeypatch.setattr(digest_mod.settings, "digest_llm_provider", "")
    monkeypatch.setattr(digest_mod.settings, "digest_llm_api_key", "")

    digest = await generate_digest(db_with_mixed_items, target_date=date.today())
    assert digest.item_count == 3
    assert "_Why:" not in digest.content  # no reason rendered when rerank is off


@pytest.mark.asyncio
async def test_digest_applies_llm_verdicts(db_with_mixed_items, monkeypatch):
    monkeypatch.setattr(digest_mod.settings, "digest_llm_provider", "openai")
    monkeypatch.setattr(digest_mod.settings, "digest_llm_api_key", "sk-test")

    async def fake_rerank(items, preferences, *, provider, api_key, **kwargs):
        from app.services.llm_filter import FilterVerdict

        return [
            FilterVerdict(item_id=item.id, kept="Drop" not in item.title, reason="r")
            for item in items
        ]

    monkeypatch.setattr(digest_mod, "rerank_candidates", fake_rerank)

    digest = await generate_digest(db_with_mixed_items, target_date=date.today())
    assert digest.item_count == 2
    assert "Drop me crypto" not in digest.content
    assert "_Why: r_" in digest.content

    # Verdict persisted on items
    from sqlalchemy import select

    result = await db_with_mixed_items.execute(select(Item).order_by(Item.id))
    for item in result.scalars():
        meta = json.loads(item.metadata_json)
        assert "llm_kept" in meta and "llm_reason" in meta


@pytest.mark.asyncio
async def test_digest_falls_back_when_rerank_raises(db_with_mixed_items, monkeypatch):
    monkeypatch.setattr(digest_mod.settings, "digest_llm_provider", "openai")
    monkeypatch.setattr(digest_mod.settings, "digest_llm_api_key", "sk-test")

    async def boom(*args, **kwargs):
        raise RuntimeError("LLM down")

    monkeypatch.setattr(digest_mod, "rerank_candidates", boom)

    digest = await generate_digest(db_with_mixed_items, target_date=date.today())
    assert digest.item_count == 3  # heuristic fallback keeps all
    assert "_Why:" not in digest.content
