"""Dump the top-N items by composite score from the live DB.

Usage:
    .venv/bin/python scripts/eval_top_items.py [N]

Useful for eyeballing ranking quality after tuning scoring weights or
adding a new source. Shows score, source slug, age, and title.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models.item import Item


async def main(limit: int) -> None:
    async with async_session() as db:
        result = await db.execute(
            select(Item)
            .options(selectinload(Item.source))
            .order_by(Item.relevance_score.desc(), Item.published_at.desc().nullslast())
            .limit(limit)
        )
        items = list(result.scalars())

    now = datetime.now(timezone.utc)
    for i in items:
        age = "?"
        if i.published_at:
            pub = i.published_at if i.published_at.tzinfo else i.published_at.replace(tzinfo=timezone.utc)
            hours = (now - pub).total_seconds() / 3600
            age = f"{hours:>5.1f}h"
        source_slug = i.source.slug if i.source else "?"
        print(
            f"[{i.relevance_score:.3f}] {age}  {source_slug:22s}  "
            f"{i.title[:90]}"
        )


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    asyncio.run(main(n))
