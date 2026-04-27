import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.digest import Digest
from app.models.item import Item
from app.models.source import Source

logger = logging.getLogger(__name__)

TOP_N = 20


async def generate_digest(db: AsyncSession, target_date: date | None = None) -> Digest:
    """Generate a daily digest of top relevant items.

    Day boundaries are anchored to UTC to match `fetched_at` storage.
    """
    target = target_date or datetime.now(timezone.utc).date()
    start = datetime.combine(target, datetime.min.time(), tzinfo=timezone.utc)
    end = start + timedelta(days=1)

    result = await db.execute(
        select(Item, Source.name)
        .join(Source, Item.source_id == Source.id)
        .where(Item.fetched_at >= start, Item.fetched_at < end)
        .order_by(Item.relevance_score.desc(), Item.points.desc().nullslast())
        .limit(TOP_N)
    )
    rows = result.all()

    sections: list[str] = [f"# AI News Digest — {target.isoformat()}\n"]

    if not rows:
        sections.append("No items collected today.\n")
    else:
        for i, (item, source_name) in enumerate(rows, 1):
            score_pct = f"{item.relevance_score * 100:.0f}%"
            points_str = f" | {item.points} pts" if item.points else ""
            sections.append(
                f"{i}. **[{item.title}]({item.url})**\n"
                f"   Source: {source_name}{points_str} | Relevance: {score_pct}\n"
                f"   {item.summary or ''}\n"
            )

    content = "\n".join(sections)

    # Upsert digest for this date
    existing = await db.execute(select(Digest).where(Digest.date == target))
    digest = existing.scalar_one_or_none()
    if digest:
        digest.content = content
        digest.item_count = len(rows)
    else:
        digest = Digest(date=target, content=content, item_count=len(rows))
        db.add(digest)

    await db.commit()
    await db.refresh(digest)
    return digest
