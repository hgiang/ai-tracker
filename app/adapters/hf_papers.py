import logging

from app.adapters.base import BaseAdapter, parse_iso_utc
from app.models.item import ContentType
from app.schemas.item import NormalizedItem

logger = logging.getLogger(__name__)

DAILY_PAPERS_URL = "https://huggingface.co/api/daily_papers"


class HFPapersAdapter(BaseAdapter):
    """Hugging Face Daily Papers — curated trending research papers.

    Uses the public JSON API, no auth required. Each paper is ranked by
    community upvotes, which is a much higher-signal curation layer than
    the raw arXiv firehose.
    """

    max_age_days = 7

    async def fetch(self, checkpoint: str | None = None) -> tuple[list[NormalizedItem], str | None]:
        data = await self._get_json(DAILY_PAPERS_URL)
        if not isinstance(data, list):
            return [], checkpoint

        items: list[NormalizedItem] = []
        latest: str | None = checkpoint

        for entry in data:
            item = _entry_to_item(entry)
            if item is None:
                continue
            items.append(item)

            published = entry.get("publishedAt")
            if published and (not latest or published > latest):
                latest = published

        logger.info("HF daily papers: %s items fetched", len(items))
        return items, latest


def _entry_to_item(entry: dict) -> NormalizedItem | None:
    paper = entry.get("paper") or {}
    arxiv_id = paper.get("id")
    if not arxiv_id:
        return None

    title = (entry.get("title") or paper.get("title") or "").strip()
    if not title:
        return None

    # Prefer the LLM-generated summary (cleaner) then fall back to the abstract.
    summary = (paper.get("ai_summary") or entry.get("summary") or paper.get("summary") or "").strip()

    keywords = paper.get("ai_keywords") or []
    if keywords:
        summary = f"{summary}\n\n🏷️ {', '.join(keywords[:6])}".strip()

    authors_list = paper.get("authors") or []
    author_names = [a.get("name", "") for a in authors_list if a.get("name")]
    author = ", ".join(author_names[:3])
    if len(author_names) > 3:
        author += f" +{len(author_names) - 3}"

    published_raw = paper.get("publishedAt") or entry.get("publishedAt")
    published_at = parse_iso_utc(published_raw) if published_raw else None

    return NormalizedItem(
        source_item_id=arxiv_id,
        url=f"https://huggingface.co/papers/{arxiv_id}",
        title=title[:500],
        summary=summary[:1500] or None,
        content_type=ContentType.PAPER,
        author=author or None,
        published_at=published_at,
        points=paper.get("upvotes"),
        comment_count=entry.get("numComments"),
    )
