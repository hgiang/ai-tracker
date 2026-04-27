from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.main import _migrate_item_duration
from app.models.source import Source
from app.routes import sources as sources_route


@pytest.mark.asyncio
async def test_migrate_item_duration_adds_missing_column(tmp_path: Path):
    db_path = tmp_path / "legacy.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE items (
                    id INTEGER NOT NULL PRIMARY KEY,
                    source_id INTEGER NOT NULL,
                    source_item_id VARCHAR(500) NOT NULL,
                    url VARCHAR(1000) NOT NULL,
                    canonical_url VARCHAR(1000) NOT NULL,
                    title VARCHAR(500) NOT NULL,
                    normalized_title VARCHAR(500) NOT NULL,
                    summary TEXT,
                    content_type VARCHAR(10) NOT NULL,
                    author VARCHAR(200),
                    published_at DATETIME,
                    fetched_at DATETIME NOT NULL,
                    relevance_score FLOAT NOT NULL,
                    points INTEGER,
                    comment_count INTEGER,
                    metadata_json TEXT,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )

    await _migrate_item_duration(engine)

    async with engine.connect() as conn:
        result = await conn.execute(text("PRAGMA table_info(items)"))
        columns = {row[1] for row in result.fetchall()}

    await engine.dispose()

    assert "duration" in columns


@pytest.mark.asyncio
async def test_sync_all_returns_partial_results_on_source_failure(db_session, monkeypatch):
    db_session.add_all(
        [
            Source(name="Good", slug="good", adapter_type="rss", url="https://example.com/good"),
            Source(name="Bad", slug="bad", adapter_type="rss", url="https://example.com/bad"),
        ]
    )
    await db_session.commit()

    async def fake_sync(source_id: int):
        if source_id == 2:
            raise RuntimeError("db insert failed")
        return sources_route.SyncResult(source="good", fetched=1, new=1, duplicates=0)

    monkeypatch.setattr(sources_route, "_sync_source_by_id", fake_sync)
    monkeypatch.setattr(sources_route, "async_session", lambda: _TestSessionCtx(db_session))

    results = await sources_route.sync_all()

    by_source = {r.source: r for r in results}
    assert by_source["good"].error is None
    assert by_source["good"].new == 1
    assert by_source["bad"].error == "db insert failed"
    assert by_source["bad"].new == 0


class _TestSessionCtx:
    """Reuse the test db_session in place of opening a new async_session()."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False
