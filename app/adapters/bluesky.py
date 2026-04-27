import logging

from app.adapters.base import BaseAdapter, parse_int, parse_iso_utc
from app.models.item import ContentType
from app.schemas.item import NormalizedItem

logger = logging.getLogger(__name__)

# Public AppView — no auth required.
FEED_URL = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"
FETCH_LIMIT = 30

# Most AI leaders don't actually post on Bluesky — they stayed on X.
# Only handles verified to post regularly are kept here.
DEFAULT_ACCOUNTS = (
    "simonwillison.net",           # Simon Willison — active AI commentary
)


class BlueskyAdapter(BaseAdapter):
    """Fetches recent posts from curated Bluesky handles via the public AppView.

    No authentication required. The source_url param is ignored — we iterate
    the configured ``accounts`` list (falling back to DEFAULT_ACCOUNTS).
    """

    max_age_days = 3

    async def fetch(self, checkpoint: str | None = None) -> tuple[list[NormalizedItem], str | None]:
        accounts = _parse_accounts(self.config.get("accounts"))
        limit = min(max(parse_int(self.config.get("limit"), FETCH_LIMIT), 5), 100)

        items: list[NormalizedItem] = []
        seen_uris: set[str] = set()
        latest_indexed: str | None = checkpoint

        for handle in accounts:
            try:
                data = await self._get_json(
                    FEED_URL,
                    params={"actor": handle, "limit": str(limit), "filter": "posts_no_replies"},
                )
            except Exception:
                logger.exception("Bluesky fetch failed for %s", handle)
                continue

            for entry in (data or {}).get("feed", []):
                # Skip reposts — entry.reason is set when the post is a repost/quote.
                if entry.get("reason"):
                    continue
                post = entry.get("post") or {}
                uri = post.get("uri")
                if not uri or uri in seen_uris:
                    continue
                seen_uris.add(uri)

                record = post.get("record") or {}
                text = (record.get("text") or "").strip()
                if not text:
                    continue

                created_at = record.get("createdAt") or post.get("indexedAt")
                published_at = parse_iso_utc(created_at) if created_at else None

                indexed_at = post.get("indexedAt")
                if indexed_at and (not latest_indexed or indexed_at > latest_indexed):
                    latest_indexed = indexed_at

                if checkpoint and indexed_at and indexed_at <= checkpoint:
                    continue

                author_handle = (post.get("author") or {}).get("handle", handle)
                rkey = uri.rsplit("/", 1)[-1]
                post_url = f"https://bsky.app/profile/{author_handle}/post/{rkey}"

                items.append(
                    NormalizedItem(
                        source_item_id=uri,
                        url=post_url,
                        title=text[:200],
                        summary=text if len(text) > 200 else None,
                        content_type=ContentType.POST,
                        author=f"@{author_handle}",
                        published_at=published_at,
                        points=post.get("likeCount"),
                        comment_count=post.get("replyCount"),
                    )
                )

        return items, latest_indexed


def _parse_accounts(value: object) -> tuple[str, ...]:
    if value is None:
        return DEFAULT_ACCOUNTS
    if isinstance(value, str) and value.strip():
        return tuple(h.strip() for h in value.split(",") if h.strip())
    return DEFAULT_ACCOUNTS
