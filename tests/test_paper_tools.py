from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.item import ContentType, Item


@pytest.fixture
def paper_item():
    return Item(
        id=1,
        source_id=1,
        source_item_id="arxiv:2501.12345",
        url="https://arxiv.org/abs/2501.12345",
        canonical_url="https://arxiv.org/abs/2501.12345",
        title="Test Paper",
        normalized_title="test paper",
        content_type=ContentType.PAPER,
        relevance_score=0.8,
        metadata_json=None,
    )


@pytest.mark.integration
async def test_summary_returns_cached(paper_item):
    import json
    paper_item.metadata_json = json.dumps({"llm_summary": "cached summary text"})

    with patch("app.routes.paper_tools.get_db"):
        with patch("app.routes.paper_tools._get_paper_item", return_value=paper_item):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/api/items/1/summary")

    assert resp.status_code == 200
    assert resp.json()["summary"] == "cached summary text"


@pytest.mark.integration
async def test_summary_returns_404_for_non_paper():
    non_paper = Item(
        id=2,
        source_id=1,
        source_item_id="hn:123",
        url="https://news.ycombinator.com/item?id=123",
        canonical_url="https://news.ycombinator.com/item?id=123",
        title="HN Post",
        normalized_title="hn post",
        content_type=ContentType.NEWS,
        relevance_score=0.5,
        metadata_json=None,
    )
    with patch("app.routes.paper_tools._get_paper_item", side_effect=HTTPException(status_code=404, detail="Item is not a paper")):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/items/2/summary")

    assert resp.status_code == 404
