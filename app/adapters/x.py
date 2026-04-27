import logging

from app.adapters.base import BaseAdapter, parse_int, parse_iso_utc
from app.config import settings
from app.models.item import ContentType
from app.schemas.item import NormalizedItem

logger = logging.getLogger(__name__)

FETCH_LIMIT = 25
MAX_PAGES = 1
SEARCH_URL = "https://api.x.com/2/tweets/search/recent"
MAX_QUERY_LEN = 480  # stay under 512-char API limit

# --- Curated AI accounts (trimmed for cost: highest-signal only) ---
AI_RESEARCHERS = (
    "karpathy",        # Andrej Karpathy
    "rasbt",           # Sebastian Raschka
    "sama",            # Sam Altman
    "ylecun",          # Yann LeCun
    "fchollet",        # Francois Chollet
    "DrJimFan",        # Jim Fan (NVIDIA)
    "demis_hassabis",  # Demis Hassabis
    "swyx",            # Swyx
    "jackclark",       # Jack Clark (Anthropic)
    "rowancheung",     # Rowan Cheung
)

AI_ORGANIZATIONS = (
    "OpenAI",
    "GoogleDeepMind",
    "GoogleAI",
    "MetaAI",
    "AnthropicAI",
    "huggingface",
)

ALL_ACCOUNTS = AI_RESEARCHERS + AI_ORGANIZATIONS


def _build_queries(accounts: tuple[str, ...], suffix: str = "-is:retweet") -> list[str]:
    """Split accounts into batched queries that fit within the API character limit."""
    queries: list[str] = []
    batch: list[str] = []
    # Base overhead: "(" + ")" + " " + suffix
    overhead = 3 + len(suffix)

    for handle in accounts:
        clause = f"from:{handle}"
        # Check if adding this handle would exceed the limit
        trial = " OR ".join([*batch, clause])
        if len(trial) + overhead > MAX_QUERY_LEN and batch:
            queries.append(f"({' OR '.join(batch)}) {suffix}")
            batch = [clause]
        else:
            batch.append(clause)

    if batch:
        queries.append(f"({' OR '.join(batch)}) {suffix}")

    return queries


class XAdapter(BaseAdapter):
    """Adapter for X (Twitter) API v2 — curated AI accounts only."""

    max_age_days = 3

    async def fetch(self, checkpoint: str | None = None) -> tuple[list[NormalizedItem], str | None]:
        if not settings.x_bearer_token:
            logger.info("Skipping X fetch because x_bearer_token is not configured")
            return [], checkpoint

        accounts = _parse_accounts(self.config.get("accounts"))
        suffix = "-is:retweet"
        queries = _build_queries(accounts, suffix) if accounts else [self.config.get("query", f"(from:karpathy) {suffix}")]

        fetch_limit = min(max(parse_int(self.config.get("max_results"), FETCH_LIMIT), 10), 100)
        max_pages = max(parse_int(self.config.get("max_pages"), MAX_PAGES), 1)
        sort_order = self.config.get("sort_order", "recency")
        headers = {"Authorization": f"Bearer {settings.x_bearer_token}"}

        all_items: list[NormalizedItem] = []
        seen_ids: set[str] = set()
        new_checkpoint = checkpoint

        for query in queries:
            items, latest_id = await self._search_query(
                query=query,
                headers=headers,
                fetch_limit=fetch_limit,
                max_pages=max_pages,
                sort_order=sort_order,
                checkpoint=checkpoint,
                seen_ids=seen_ids,
            )
            all_items.extend(items)
            if latest_id and (not new_checkpoint or latest_id > new_checkpoint):
                new_checkpoint = latest_id

        return all_items, new_checkpoint

    async def _search_query(
        self,
        *,
        query: str,
        headers: dict[str, str],
        fetch_limit: int,
        max_pages: int,
        sort_order: str,
        checkpoint: str | None,
        seen_ids: set[str],
    ) -> tuple[list[NormalizedItem], str | None]:
        base_params = {
            "query": query,
            "max_results": str(fetch_limit),
            "sort_order": sort_order,
            "tweet.fields": "created_at,public_metrics,author_id,text",
            "user.fields": "username",
            "expansions": "author_id",
        }
        if checkpoint:
            base_params["since_id"] = checkpoint

        items: list[NormalizedItem] = []
        next_token: str | None = None
        latest_id: str | None = None

        for page in range(max_pages):
            params = dict(base_params)
            if next_token:
                params["next_token"] = next_token

            data, response_headers = await self._get_json_with_headers(
                SEARCH_URL, headers=headers, params=params
            )
            _log_rate_limit(query, response_headers, page + 1)

            tweets = data.get("data", [])
            users_list = data.get("includes", {}).get("users", [])
            users_map = {u["id"]: u["username"] for u in users_list}
            meta = data.get("meta", {})

            if page == 0:
                latest_id = meta.get("newest_id") or (tweets[0]["id"] if tweets else None)

            for tweet in tweets:
                tweet_id = tweet.get("id")
                if not tweet_id or tweet_id in seen_ids:
                    continue
                seen_ids.add(tweet_id)

                text = tweet.get("text", "")
                metrics = tweet.get("public_metrics", {})
                author_id = tweet.get("author_id", "")
                username = users_map.get(author_id, author_id)

                published_at = parse_iso_utc(tweet["created_at"]) if tweet.get("created_at") else None

                items.append(
                    NormalizedItem(
                        source_item_id=tweet_id,
                        url=f"https://x.com/{username}/status/{tweet_id}",
                        title=text[:200],
                        summary=text if len(text) > 200 else None,
                        content_type=ContentType.POST,
                        author=f"@{username}",
                        published_at=published_at,
                        points=metrics.get("like_count"),
                        comment_count=metrics.get("reply_count"),
                    )
                )

            next_token = meta.get("next_token")
            if not next_token:
                break

        return items, latest_id


def _parse_accounts(value: object) -> tuple[str, ...]:
    """Parse accounts config — accepts comma-separated string or None (uses ALL_ACCOUNTS)."""
    if value is None:
        return ALL_ACCOUNTS
    if isinstance(value, str) and value.strip():
        return tuple(h.strip().lstrip("@") for h in value.split(",") if h.strip())
    return ALL_ACCOUNTS


def _log_rate_limit(query: str, headers: dict[str, str], page: int) -> None:
    remaining = headers.get("x-rate-limit-remaining")
    reset = headers.get("x-rate-limit-reset")
    if remaining is None and reset is None:
        return
    logger.info(
        "X recent search page=%s remaining=%s reset=%s query=%s",
        page,
        remaining,
        reset,
        query[:80],
    )
