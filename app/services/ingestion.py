import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.registry import get_adapter
from app.models.item import Item
from app.models.source import Source, SourceCheckpoint
from app.schemas.item import NormalizedItem
from app.schemas.source import SyncResult
from app.services.relevance import canonicalize_url, compute_composite_score, normalize_title

logger = logging.getLogger(__name__)
CHECKPOINT_KEY = "last_sync"

# Cross-source convergence: boost per additional source that covers the same story.
CONVERGENCE_BOOST_PER_HIT = 0.05
CONVERGENCE_BOOST_CAP = 0.15


async def sync_source(db: AsyncSession, source: Source) -> SyncResult:
    """Fetch items from a source and persist new ones."""
    checkpoint = await _get_checkpoint(db, source.id)
    config = json.loads(source.config_json) if source.config_json else {}
    adapter = get_adapter(source.adapter_type, source.url, **config)

    try:
        raw_items, new_checkpoint = await adapter.fetch(checkpoint)
    except Exception:
        logger.exception("Failed to fetch from %s", source.slug)
        return SyncResult(source=source.slug, fetched=0, new=0, duplicates=0)

    prepared_items = [
        _PreparedItem(
            raw=raw,
            canonical_url=canonicalize_url(raw.url),
            normalized_title=normalize_title(raw.title),
        )
        for raw in adapter.filter_recent(raw_items)
    ]
    duplicate_state = await _load_duplicate_state(db, source.id, prepared_items)
    source_slug_by_id = await _load_source_slugs(db)

    new_count = 0
    dup_count = 0
    converged_count = 0

    for prepared in prepared_items:
        existing = _find_existing(duplicate_state, prepared)
        if existing is not None:
            if existing.source_id != source.id:
                existing_family = _source_family(source_slug_by_id.get(existing.source_id, ""))
                if existing_family != _source_family(source.slug):
                    _apply_convergence_boost(existing, source.slug)
                    converged_count += 1
                else:
                    dup_count += 1
            else:
                dup_count += 1
            continue

        raw = prepared.raw
        score = compute_composite_score(
            title=raw.title,
            summary=raw.summary,
            published_at=raw.published_at,
            points=raw.points,
            comment_count=raw.comment_count,
            source_slug=source.slug,
        )

        item = Item(
            source_id=source.id,
            source_item_id=raw.source_item_id,
            url=raw.url,
            canonical_url=prepared.canonical_url,
            title=raw.title,
            normalized_title=prepared.normalized_title,
            summary=raw.summary,
            content_type=raw.content_type,
            author=raw.author,
            published_at=raw.published_at,
            fetched_at=datetime.now(timezone.utc),
            relevance_score=score,
            points=raw.points,
            comment_count=raw.comment_count,
            duration=raw.duration,
            metadata_json=raw.metadata_json,
        )
        db.add(item)
        new_count += 1
        duplicate_state.source_item_ids[raw.source_item_id] = item
        duplicate_state.canonical_urls[prepared.canonical_url] = item
        duplicate_state.normalized_titles[prepared.normalized_title] = item

    if new_checkpoint:
        await _set_checkpoint(db, source.id, new_checkpoint)

    await db.commit()

    if converged_count:
        logger.info(
            "Source %s converged with %s existing items from other sources",
            source.slug,
            converged_count,
        )

    return SyncResult(
        source=source.slug,
        fetched=len(prepared_items),
        new=new_count,
        duplicates=dup_count,
        converged=converged_count,
    )


@dataclass(slots=True)
class _PreparedItem:
    raw: NormalizedItem
    canonical_url: str
    normalized_title: str


@dataclass(slots=True)
class _DuplicateState:
    source_item_ids: dict[str, Item] = field(default_factory=dict)
    canonical_urls: dict[str, Item] = field(default_factory=dict)
    normalized_titles: dict[str, Item] = field(default_factory=dict)


async def _load_duplicate_state(
    db: AsyncSession, source_id: int, items: list[_PreparedItem]
) -> "_DuplicateState":
    source_item_ids = {item.raw.source_item_id for item in items}
    canonical_urls = {item.canonical_url for item in items}
    normalized_titles = {item.normalized_title for item in items}

    state = _DuplicateState()

    if source_item_ids:
        result = await db.execute(
            select(Item).where(
                Item.source_id == source_id,
                Item.source_item_id.in_(source_item_ids),
            )
        )
        for row in result.scalars():
            state.source_item_ids[row.source_item_id] = row

    if canonical_urls:
        result = await db.execute(
            select(Item).where(Item.canonical_url.in_(canonical_urls))
        )
        for row in result.scalars():
            state.canonical_urls[row.canonical_url] = row

    if normalized_titles:
        result = await db.execute(
            select(Item).where(Item.normalized_title.in_(normalized_titles))
        )
        for row in result.scalars():
            state.normalized_titles[row.normalized_title] = row

    return state


def _find_existing(state: "_DuplicateState", item: _PreparedItem) -> Item | None:
    """Return an existing Item that matches this prepared item, or None."""
    return (
        state.source_item_ids.get(item.raw.source_item_id)
        or state.canonical_urls.get(item.canonical_url)
        or state.normalized_titles.get(item.normalized_title)
    )


def _apply_convergence_boost(existing: Item, incoming_source_slug: str) -> None:
    """Boost relevance_score and track converged sources in metadata_json."""
    meta = _load_meta(existing.metadata_json)
    converged: list[str] = meta.get("converged_sources", []) or []
    if incoming_source_slug in converged:
        return  # already counted this source
    converged.append(incoming_source_slug)
    meta["converged_sources"] = converged

    boost = min(CONVERGENCE_BOOST_PER_HIT * len(converged), CONVERGENCE_BOOST_CAP)
    base = meta.get("base_relevance_score")
    if base is None:
        base = existing.relevance_score
        meta["base_relevance_score"] = base
    existing.relevance_score = min(round(base + boost, 4), 1.0)
    existing.metadata_json = json.dumps(meta)


async def _load_source_slugs(db: AsyncSession) -> dict[int, str]:
    result = await db.execute(select(Source.id, Source.slug))
    return {row_id: slug for row_id, slug in result.all()}


def _source_family(slug: str) -> str:
    """Group related sources so intra-family matches don't count as convergence.

    e.g. arxiv-csai + arxiv-cscl share the 'arxiv' family; reddit-ml + reddit-openai
    share 'reddit'. Different families (arxiv vs reddit vs hackernews) still converge.
    """
    if not slug:
        return ""
    return slug.split("-", 1)[0]


def _load_meta(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


async def _get_checkpoint(db: AsyncSession, source_id: int) -> str | None:
    result = await db.execute(
        select(SourceCheckpoint.checkpoint_value).where(
            SourceCheckpoint.source_id == source_id,
            SourceCheckpoint.checkpoint_key == CHECKPOINT_KEY,
        )
    )
    return result.scalar_one_or_none()


async def _set_checkpoint(db: AsyncSession, source_id: int, value: str) -> None:
    result = await db.execute(
        select(SourceCheckpoint).where(
            SourceCheckpoint.source_id == source_id,
            SourceCheckpoint.checkpoint_key == CHECKPOINT_KEY,
        )
    )
    cp = result.scalar_one_or_none()
    if cp:
        cp.checkpoint_value = value
    else:
        db.add(
            SourceCheckpoint(
                source_id=source_id,
                checkpoint_key=CHECKPOINT_KEY,
                checkpoint_value=value,
            )
        )
