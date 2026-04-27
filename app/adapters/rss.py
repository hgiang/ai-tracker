import asyncio
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import feedparser

from app.adapters.base import USER_AGENT, BaseAdapter
from app.models.item import ContentType
from app.schemas.item import NormalizedItem

_CURL_MAX_TIME = 30


class RSSAdapter(BaseAdapter):
    async def fetch(self, checkpoint: str | None = None) -> tuple[list[NormalizedItem], str | None]:
        text = await self._fetch_feed_text()
        feed = feedparser.parse(text)
        entries = feed.entries

        new_checkpoint = None
        items: list[NormalizedItem] = []

        # Note: we intentionally do NOT break on `entry_id == checkpoint`.
        # Some feeds (notably Reddit /hot.rss) are ordered by popularity, not
        # time, and pin stickied posts to the top. Breaking on the checkpoint
        # would stop on the same stickied post every sync and miss all new
        # items below it. Deduplication is handled by the ingestion layer
        # via source_item_id / canonical_url / normalized_title.
        for entry in entries:
            entry_id = entry.get("id", entry.get("link", ""))
            if new_checkpoint is None:
                new_checkpoint = entry_id

            pub_dt = _parse_date(entry)
            summary = entry.get("summary", "")
            content = (entry.get("content") or [{}])[0].get("value", "")
            is_long = len(content or summary) > 500

            content_type = _resolve_content_type(self.config.get("content_type"), is_long)
            duration = _parse_duration(entry) if content_type == ContentType.PODCAST else None

            items.append(
                NormalizedItem(
                    source_item_id=entry_id,
                    url=entry.get("link", ""),
                    title=entry.get("title", ""),
                    summary=(summary or content)[:500],
                    content_type=content_type,
                    author=entry.get("author"),
                    published_at=pub_dt,
                    duration=duration,
                )
            )
        return items, new_checkpoint or checkpoint

    async def _fetch_feed_text(self) -> str:
        headers = {"User-Agent": USER_AGENT}
        if _needs_browser_client(self.source_url):
            return await _get_text_with_curl(self.source_url, headers=headers)
        return await self._get_text(self.source_url, headers=headers)


async def _get_text_with_curl(url: str, headers: dict[str, str]) -> str:
    args = ["curl", "-fsSL", "--max-time", str(_CURL_MAX_TIME), url]
    for key, value in headers.items():
        args.extend(["-H", f"{key}: {value}"])
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_CURL_MAX_TIME + 5)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise
    if proc.returncode != 0:
        message = stderr.decode("utf-8", errors="replace").strip() or f"curl exited {proc.returncode}"
        raise RuntimeError(message)
    return stdout.decode("utf-8", errors="replace")


def _needs_browser_client(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "reddit.com" or host.endswith(".reddit.com")


def _parse_duration(entry: object) -> str | None:
    """Extract and normalise itunes:duration to HH:MM:SS or MM:SS."""
    raw = getattr(entry, "itunes_duration", None)
    if not raw:
        return None
    raw = str(raw).strip()
    if ":" in raw:
        return raw
    try:
        total = int(raw)
        hours, remainder = divmod(total, 3600)
        mins, secs = divmod(remainder, 60)
        if hours:
            return f"{hours}:{mins:02d}:{secs:02d}"
        return f"{mins}:{secs:02d}"
    except ValueError:
        return raw or None


def _resolve_content_type(config_type: str | None, is_long: bool) -> ContentType:
    """Return ContentType from config override, or auto-detect from content length."""
    if config_type:
        try:
            return ContentType(config_type)
        except ValueError:
            pass
    return ContentType.ARTICLE if is_long else ContentType.NEWS


def _parse_date(entry: object) -> datetime | None:
    for attr in ("published", "updated"):
        raw = getattr(entry, attr, None)
        if not raw:
            continue
        # Try RFC 2822 first (standard RSS), then ISO 8601 (Atom/Reddit)
        try:
            return parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            pass
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            pass
    return None
