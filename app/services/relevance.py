import math
import re
import unicodedata
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from app.config import settings

_KEYWORDS: list[str] | None = None
_TRACKING_KEYS = frozenset({"utm_source", "utm_medium", "utm_campaign", "utm_content", "ref", "source"})

# --- Composite score weights (sum to 1.0) ---
W_KEYWORD = 0.30
W_RECENCY = 0.30
W_ENGAGEMENT = 0.25
W_AUTHORITY = 0.15

# Recency half-life: score halves every N hours
RECENCY_HALF_LIFE_HOURS = 48.0
# Engagement saturates at this many points (log-normalized)
ENGAGEMENT_SATURATION = 500.0

# Per-source authority (0..1). Unknown sources default to 0.5.
SOURCE_AUTHORITY: dict[str, float] = {
    "hackernews": 0.85,
    "arxiv-csai": 0.80,
    "arxiv-cscl": 0.80,
    "arxiv-csma": 0.75,
    "openai-blog": 0.95,
    "anthropic-blog": 0.95,
    "google-ai-blog": 0.90,
    "hf-blog": 0.85,
    "github-ai": 0.75,
    "x-ai-leaders": 0.80,
    "bluesky-ai": 0.75,
    "polymarket-ai": 0.30,
    "hf-papers": 0.90,
    "reddit-ml": 0.70,
    "reddit-localllama": 0.65,
    "reddit-openai": 0.55,
    "reddit-claudeai": 0.55,
    "reddit-chatgpt": 0.45,
    "reddit-artificial": 0.50,
    "reddit-deeplearning": 0.55,
    "reddit-languagetechnology": 0.55,
}


def _get_keywords() -> list[str]:
    global _KEYWORDS
    if _KEYWORDS is None:
        _KEYWORDS = settings.keywords_list
    return _KEYWORDS


def normalize_title(title: str) -> str:
    """Lowercase, strip accents, collapse whitespace, remove punctuation."""
    text = title.lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def canonicalize_url(url: str) -> str:
    """Remove tracking params and fragments to get a canonical URL."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    cleaned = {k: v for k, v in params.items() if k not in _TRACKING_KEYS}
    clean_query = urlencode(cleaned, doseq=True)
    return urlunparse(parsed._replace(query=clean_query, fragment=""))


def compute_keyword_score(title: str, summary: str | None) -> float:
    """Score 0.0-1.0 based on keyword matches in title and summary.

    Saturates quickly — a single title hit already scores 0.5, so that
    topically-relevant items aren't dominated by generic high-engagement noise.
    """
    keywords = _get_keywords()
    if not keywords:
        return 0.5

    title_lower = title.lower()
    text = f"{title_lower} {(summary or '').lower()}"
    body_hits = sum(1 for kw in keywords if kw in text)
    title_hits = sum(1 for kw in keywords if kw in title_lower)

    if body_hits == 0:
        return 0.0

    # Title hits count double. Saturate at ~3 total weighted hits.
    weighted = body_hits + title_hits
    return min(weighted / 3.0, 1.0)


def compute_recency_score(published_at: datetime | None, now: datetime | None = None) -> float:
    """Exponential decay: 1.0 at publish time, 0.5 after RECENCY_HALF_LIFE_HOURS."""
    if published_at is None:
        return 0.3  # neutral prior for items without timestamps
    now = now or datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    age_hours = max((now - published_at).total_seconds() / 3600.0, 0.0)
    return 0.5 ** (age_hours / RECENCY_HALF_LIFE_HOURS)


def compute_engagement_score(points: int | None, comment_count: int | None) -> float:
    """Log-normalized engagement. Saturates around ENGAGEMENT_SATURATION points."""
    signal = (points or 0) + 2 * (comment_count or 0)
    if signal <= 0:
        return 0.0
    return min(math.log1p(signal) / math.log1p(ENGAGEMENT_SATURATION), 1.0)


def compute_authority_score(source_slug: str) -> float:
    return SOURCE_AUTHORITY.get(source_slug, 0.5)


def compute_composite_score(
    *,
    title: str,
    summary: str | None,
    published_at: datetime | None,
    points: int | None,
    comment_count: int | None,
    source_slug: str,
    now: datetime | None = None,
) -> float:
    """Weighted composite of keyword, recency, engagement, and source authority."""
    kw = compute_keyword_score(title, summary)
    rec = compute_recency_score(published_at, now)
    eng = compute_engagement_score(points, comment_count)
    auth = compute_authority_score(source_slug)
    return round(
        W_KEYWORD * kw + W_RECENCY * rec + W_ENGAGEMENT * eng + W_AUTHORITY * auth,
        4,
    )


# Back-compat alias — existing callers use this name.
def compute_relevance_score(title: str, summary: str | None) -> float:
    return compute_keyword_score(title, summary)
