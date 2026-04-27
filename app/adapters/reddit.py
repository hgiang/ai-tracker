import logging
from datetime import datetime, timezone

import httpx

from app.adapters.base import USER_AGENT, BaseAdapter
from app.config import settings
from app.models.item import ContentType
from app.schemas.item import NormalizedItem

logger = logging.getLogger(__name__)

FETCH_LIMIT = 50
COMMENT_ENRICHMENT_LIMIT = 15
TOP_COMMENTS_PER_POST = 2
BOT_AUTHORS = frozenset({
    "automoderator", "withoutreason1729", "b0tr4p1st", "savevideo",
    "remindmebot", "sneakpeekbot",
})
MIN_COMMENTS_FOR_ENRICHMENT = 3


class RedditAdapter(BaseAdapter):

    max_age_days = 2

    async def fetch(self, checkpoint: str | None = None) -> tuple[list[NormalizedItem], str | None]:
        subreddit = self.config.get("subreddit", "MachineLearning")
        headers = {"User-Agent": USER_AGENT}

        if settings.reddit_client_id and settings.reddit_client_secret:
            token = await self._get_oauth_token()
            headers["Authorization"] = f"Bearer {token}"
            url = f"https://oauth.reddit.com/r/{subreddit}/hot?limit={FETCH_LIMIT}&raw_json=1"
        else:
            url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={FETCH_LIMIT}&raw_json=1"

        data = await self._get_json(url, headers=headers)
        posts = data.get("data", {}).get("children", [])

        # Skip stickied posts for checkpoint — they stay at the top of /hot
        # permanently and would cause the checkpoint to match on every sync.
        first_non_sticky = next(
            (p for p in posts if not p["data"].get("stickied", False)), None
        )
        new_checkpoint = first_non_sticky["data"]["name"] if first_non_sticky else checkpoint

        items: list[NormalizedItem] = []
        enriched_count = 0
        for idx, post in enumerate(posts):
            p = post["data"]
            if p.get("stickied", False):
                continue
            if p["name"] == checkpoint:
                break
            is_self = p.get("is_self", False)
            selftext = (p.get("selftext", "") or "").strip()
            permalink_path = p.get("permalink", "")
            permalink = f"https://www.reddit.com{permalink_path}"
            num_comments = p.get("num_comments", 0) or 0

            comments_text: str | None = None
            if (
                idx < COMMENT_ENRICHMENT_LIMIT
                and num_comments >= MIN_COMMENTS_FOR_ENRICHMENT
                and permalink_path
            ):
                comments_text = await self._fetch_top_comments(permalink_path, headers)
                if comments_text:
                    enriched_count += 1

            summary = _build_summary(selftext if is_self else None, comments_text)

            post_url = permalink if is_self else _resolve_url(p.get("url"), permalink)
            items.append(
                NormalizedItem(
                    source_item_id=p["name"],
                    url=post_url,
                    title=p.get("title", ""),
                    summary=summary,
                    content_type=ContentType.DISCUSSION if is_self else ContentType.NEWS,
                    author=p.get("author"),
                    published_at=datetime.fromtimestamp(p.get("created_utc", 0), tz=timezone.utc),
                    points=p.get("score"),
                    comment_count=num_comments,
                )
            )

        if enriched_count:
            logger.info("Reddit %s: enriched %s posts with top comments", subreddit, enriched_count)
        return items, new_checkpoint

    async def _fetch_top_comments(
        self, permalink_path: str, headers: dict[str, str]
    ) -> str | None:
        """Return a formatted string of top N comments for a post."""
        if "Authorization" in headers:
            url = f"https://oauth.reddit.com{permalink_path}?limit={TOP_COMMENTS_PER_POST}&sort=top&raw_json=1"
        else:
            url = f"https://www.reddit.com{permalink_path.rstrip('/')}.json?limit={TOP_COMMENTS_PER_POST}&sort=top&raw_json=1"

        try:
            data = await self._get_json(url, headers=headers)
        except Exception:
            logger.debug("Failed to fetch comments for %s", permalink_path)
            return None

        if not isinstance(data, list) or len(data) < 2:
            return None

        children = data[1].get("data", {}).get("children", [])
        lines: list[str] = []
        for child in children:
            if len(lines) >= TOP_COMMENTS_PER_POST:
                break
            if child.get("kind") != "t1":
                continue
            c = child.get("data", {})
            author = (c.get("author") or "anon")
            if author.lower() in BOT_AUTHORS or author.lower().endswith("bot"):
                continue
            body = (c.get("body") or "").strip()
            if not body or body in ("[deleted]", "[removed]"):
                continue
            score = c.get("score", 0)
            snippet = body[:300].replace("\n", " ")
            lines.append(f"💬 u/{author} ({score}↑): {snippet}")

        return "\n".join(lines) if lines else None

    async def _get_oauth_token(self) -> str:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=(settings.reddit_client_id, settings.reddit_client_secret),
                data={"grant_type": "client_credentials"},
                headers={"User-Agent": USER_AGENT},
            )
            resp.raise_for_status()
            return resp.json()["access_token"]


_MEDIA_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".mov", ".pgn"})
_MEDIA_HOSTS = frozenset({"i.redd.it", "preview.redd.it", "i.imgur.com", "v.redd.it"})


def _resolve_url(external_url: str | None, permalink: str) -> str:
    """Return the Reddit permalink when the external URL is a raw media file."""
    if not external_url:
        return permalink
    try:
        from urllib.parse import urlparse
        parsed = urlparse(external_url)
        if parsed.netloc in _MEDIA_HOSTS:
            return permalink
        path = parsed.path.lower()
        if any(path.endswith(ext) for ext in _MEDIA_EXTENSIONS):
            return permalink
    except Exception:
        pass
    return external_url


def _build_summary(selftext: str | None, comments: str | None) -> str | None:
    """Combine optional selftext with top-comment snippets."""
    parts: list[str] = []
    if selftext:
        parts.append(selftext[:500])
    if comments:
        parts.append(comments)
    if not parts:
        return None
    return "\n\n".join(parts)[:1500]
