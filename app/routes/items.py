from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.item import ContentType, Item
from app.models.source import SourceCheckpoint
from app.schemas.item import ItemList, ItemOut

router = APIRouter(prefix="/items", tags=["items"])


@router.get("", response_model=ItemList)
async def list_items(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    content_type: ContentType | None = None,
    source_id: int | None = None,
    min_score: float | None = None,
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    filters = []
    if content_type:
        filters.append(Item.content_type == content_type)
    if source_id:
        filters.append(Item.source_id == source_id)
    if min_score is not None:
        filters.append(Item.relevance_score >= min_score)
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like_q = f"%{escaped}%"
        filters.append(
            Item.title.ilike(like_q, escape="\\") | Item.summary.ilike(like_q, escape="\\")
        )

    total = (await db.execute(select(func.count(Item.id)).where(*filters))).scalar_one()
    offset = (page - 1) * limit
    result = await db.execute(
        select(Item)
        .where(*filters)
        .order_by(Item.relevance_score.desc(), Item.published_at.desc().nullslast(), Item.id.desc())
        .offset(offset)
        .limit(limit)
    )
    items = list(result.scalars().all())
    return {"items": items, "total": total, "page": page, "limit": limit}


@router.post("/clear")
async def clear_all_items(db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(delete(Item))
    await db.execute(delete(SourceCheckpoint))
    await db.commit()
    return {"deleted": result.rowcount}


@router.get("/{item_id}", response_model=ItemOut)
async def get_item(item_id: int, db: AsyncSession = Depends(get_db)) -> Item:
    result = await db.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item
