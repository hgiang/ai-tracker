import asyncio
from datetime import datetime, timezone

from app.adapters.base import BaseAdapter
from app.models.item import ContentType
from app.schemas.item import NormalizedItem

HN_TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{}.json"
FETCH_LIMIT = 50


class HackerNewsAdapter(BaseAdapter):
    async def fetch(self, checkpoint: str | None = None) -> tuple[list[NormalizedItem], str | None]:
        story_ids = await self._get_json(HN_TOP_URL)
        story_ids = story_ids[:FETCH_LIMIT]

        last_seen = int(checkpoint) if checkpoint else 0
        new_checkpoint = str(story_ids[0]) if story_ids else checkpoint

        ids_to_fetch = [sid for sid in story_ids if sid > last_seen]
        stories = await asyncio.gather(
            *(self._get_json(HN_ITEM_URL.format(sid)) for sid in ids_to_fetch),
            return_exceptions=True,
        )

        items: list[NormalizedItem] = []
        for sid, story in zip(ids_to_fetch, stories):
            if isinstance(story, Exception) or not story or story.get("type") != "story":
                continue
            url = f"https://news.ycombinator.com/item?id={sid}"
            title = story.get("title", "")
            is_discussion = not story.get("url") or title.startswith(("Ask HN", "Show HN", "Tell HN"))
            items.append(
                NormalizedItem(
                    source_item_id=str(sid),
                    url=url,
                    title=title,
                    summary=story.get("text"),
                    content_type=ContentType.DISCUSSION if is_discussion else ContentType.NEWS,
                    author=story.get("by"),
                    published_at=datetime.fromtimestamp(story.get("time", 0), tz=timezone.utc),
                    points=story.get("score"),
                    comment_count=story.get("descendants"),
                )
            )
        return items, new_checkpoint
