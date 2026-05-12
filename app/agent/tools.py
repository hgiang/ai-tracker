"""Agent-callable tools.

These wrap existing services into pure async functions with explicit
Pydantic input/output schemas, suitable for LLM tool-calling loops.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ContentType, Item
from app.schemas.item import ItemList, ItemOut


async def search_items(
    db: AsyncSession,
    *,
    query: str | None = None,
    content_type: ContentType | None = None,
    source_id: int | None = None,
    min_score: float | None = None,
    page: int = 1,
    limit: int = 20,
) -> ItemList:
    """Search ingested items in the local corpus.

    Performs a case-insensitive substring match on title and summary,
    optionally filtered by content type, source, and minimum relevance
    score. Results are ordered by relevance, then publish date.

    Args:
        db: Active async SQLAlchemy session.
        query: Free-text query matched against title and summary.
        content_type: Restrict to a single content type (e.g. PAPER).
        source_id: Restrict to a single source.
        min_score: Lower bound for relevance_score (0.0-1.0).
        page: 1-indexed page number.
        limit: Page size, 1-100.

    Returns:
        An ItemList containing the page of items, total count, page,
        and limit.
    """
    if page < 1:
        raise ValueError("page must be >= 1")
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")

    filters = []
    if content_type is not None:
        filters.append(Item.content_type == content_type)
    if source_id is not None:
        filters.append(Item.source_id == source_id)
    if min_score is not None:
        filters.append(Item.relevance_score >= min_score)
    if query:
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like_q = f"%{escaped}%"
        filters.append(
            Item.title.ilike(like_q, escape="\\")
            | Item.summary.ilike(like_q, escape="\\")
        )

    total = (await db.execute(select(func.count(Item.id)).where(*filters))).scalar_one()
    offset = (page - 1) * limit
    result = await db.execute(
        select(Item)
        .where(*filters)
        .order_by(
            Item.relevance_score.desc(),
            Item.published_at.desc().nullslast(),
            Item.id.desc(),
        )
        .offset(offset)
        .limit(limit)
    )
    items = [ItemOut.model_validate(row) for row in result.scalars().all()]
    return ItemList(items=items, total=total, page=page, limit=limit)
