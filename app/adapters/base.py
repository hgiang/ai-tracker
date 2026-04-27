import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone

import httpx

from app.schemas.item import NormalizedItem

MAX_AGE_DAYS = 7
USER_AGENT = "ai-tracker:0.1.0 (personal news aggregator)"
logger = logging.getLogger(__name__)

_shared_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(timeout=30.0)
    return _shared_client


async def close_shared_client() -> None:
    global _shared_client
    if _shared_client is not None and not _shared_client.is_closed:
        await _shared_client.aclose()
        _shared_client = None


def age_cutoff() -> datetime:
    """Return the UTC datetime cutoff for MAX_AGE_DAYS."""
    return datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)


def parse_iso_utc(ts: str) -> datetime:
    """Parse an ISO 8601 timestamp, handling trailing 'Z'."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def parse_int(value: object, default: int) -> int:
    """Safely coerce a value to int, returning default on failure."""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class BaseAdapter(ABC):
    """Base class for all source adapters.

    Adapters only fetch and normalize data. They do not handle persistence.
    """

    def __init__(self, source_url: str, **kwargs: str) -> None:
        self.source_url = source_url
        self.config = kwargs

    max_age_days: int = MAX_AGE_DAYS

    @classmethod
    def filter_recent(cls, items: list[NormalizedItem]) -> list[NormalizedItem]:
        """Drop items older than max_age_days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=cls.max_age_days)
        return [i for i in items if i.published_at is None or i.published_at >= cutoff]

    @abstractmethod
    async def fetch(self, checkpoint: str | None = None) -> tuple[list[NormalizedItem], str | None]:
        """Fetch items from the source.

        Args:
            checkpoint: Optional checkpoint value from last sync.

        Returns:
            Tuple of (normalized items, new checkpoint value).
        """

    async def _request(self, url: str, **kwargs: object) -> httpx.Response:
        client = _get_client()
        resp = await client.get(url, **kwargs)
        if resp.status_code == 429:
            logger.warning(
                "Rate limited by %s (retry-after=%s, reset=%s)",
                url,
                resp.headers.get("retry-after"),
                resp.headers.get("x-rate-limit-reset"),
            )
        resp.raise_for_status()
        return resp

    async def _get_json(self, url: str, **kwargs: object) -> object:
        resp = await self._request(url, **kwargs)
        return resp.json()

    async def _get_json_with_headers(
        self, url: str, **kwargs: object
    ) -> tuple[object, dict[str, str]]:
        resp = await self._request(url, **kwargs)
        return resp.json(), dict(resp.headers)

    async def _get_text(self, url: str, **kwargs: object) -> str:
        resp = await self._request(url, **kwargs)
        return resp.text
