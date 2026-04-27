import logging

from app.adapters.base import BaseAdapter, parse_int, parse_iso_utc
from app.models.item import ContentType
from app.schemas.item import NormalizedItem

logger = logging.getLogger(__name__)

GAMMA_MARKETS_URL = "https://gamma-api.polymarket.com/markets"
# Tag IDs to fetch. GPT-5 tag (102464) currently surfaces ~25 AI model / lab
# prediction markets. Multiple tag IDs can be passed via config.
DEFAULT_TAG_IDS = ("102464",)
DEFAULT_LIMIT = 30


class PolymarketAdapter(BaseAdapter):
    """Polymarket AI prediction-market adapter.

    Fetches open markets tagged AI/GPT-5 and surfaces them as items whose
    title encodes the current Yes-outcome probability. No auth required.
    """

    max_age_days = 30  # markets live for weeks/months; don't age-filter

    async def fetch(self, checkpoint: str | None = None) -> tuple[list[NormalizedItem], str | None]:
        tag_ids = _parse_tag_ids(self.config.get("tag_ids"))
        limit = min(max(parse_int(self.config.get("limit"), DEFAULT_LIMIT), 5), 100)

        items: list[NormalizedItem] = []
        seen_ids: set[str] = set()
        latest_updated: str | None = checkpoint

        for tag_id in tag_ids:
            try:
                data = await self._get_json(
                    GAMMA_MARKETS_URL,
                    params={
                        "closed": "false",
                        "tag_id": tag_id,
                        "order": "volume",
                        "ascending": "false",
                        "limit": str(limit),
                    },
                )
            except Exception:
                logger.exception("Polymarket fetch failed for tag_id=%s", tag_id)
                continue

            for market in data or []:
                market_id = str(market.get("id", ""))
                if not market_id or market_id in seen_ids:
                    continue
                seen_ids.add(market_id)

                item = _market_to_item(market)
                if item is None:
                    continue
                items.append(item)

                updated = market.get("updatedAt")
                if updated and (not latest_updated or updated > latest_updated):
                    latest_updated = updated

        return items, latest_updated


def _market_to_item(market: dict) -> NormalizedItem | None:
    question = (market.get("question") or "").strip()
    if not question:
        return None
    slug = market.get("slug") or market.get("id")
    url = f"https://polymarket.com/event/{slug}"

    yes_pct = _extract_yes_price(market)
    title = f"🎲 {question}"
    if yes_pct is not None:
        title = f"🎲 [{yes_pct}% Yes] {question}"

    volume = _parse_float(market.get("volume"))
    volume_24h = _parse_float(market.get("volume24hr"))
    liquidity = _parse_float(market.get("liquidity"))

    description = (market.get("description") or "").strip()
    stats_line = (
        f"Volume: ${volume:,.0f} · 24h: ${volume_24h:,.0f} · Liquidity: ${liquidity:,.0f}"
    )
    summary_parts = [stats_line]
    if description:
        summary_parts.append(description[:600])
    summary = "\n\n".join(summary_parts)

    updated_at = market.get("updatedAt") or market.get("startDate")
    published_at = parse_iso_utc(updated_at) if updated_at else None

    return NormalizedItem(
        source_item_id=str(market["id"]),
        url=url,
        title=title[:500],
        summary=summary[:1500],
        content_type=ContentType.NEWS,
        author="Polymarket",
        published_at=published_at,
        points=int(volume),
        comment_count=int(volume_24h),
    )


def _extract_yes_price(market: dict) -> int | None:
    """Extract the Yes-outcome price as an integer percentage."""
    prices_raw = market.get("outcomePrices")
    outcomes_raw = market.get("outcomes")
    if not prices_raw or not outcomes_raw:
        return None

    # Gamma sometimes returns these as JSON-encoded strings.
    import json as _json

    prices = prices_raw
    outcomes = outcomes_raw
    if isinstance(prices, str):
        try:
            prices = _json.loads(prices)
        except _json.JSONDecodeError:
            return None
    if isinstance(outcomes, str):
        try:
            outcomes = _json.loads(outcomes)
        except _json.JSONDecodeError:
            return None

    try:
        for outcome, price in zip(outcomes, prices, strict=True):
            if str(outcome).strip().lower() == "yes":
                return round(float(price) * 100)
    except (TypeError, ValueError):
        return None
    return None


def _parse_float(value: object) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_tag_ids(value: object) -> tuple[str, ...]:
    if value is None:
        return DEFAULT_TAG_IDS
    if isinstance(value, str) and value.strip():
        return tuple(v.strip() for v in value.split(",") if v.strip())
    if isinstance(value, (list, tuple)):
        return tuple(str(v) for v in value if str(v).strip())
    return DEFAULT_TAG_IDS
