import json
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.digest import Digest
from app.models.item import Item
from app.models.source import Source
from app.services.llm_client import Provider
from app.services.llm_filter import CandidateItem, FilterVerdict, rerank_candidates
from app.services.preferences import load_preferences_cached

logger = logging.getLogger(__name__)


async def generate_digest(db: AsyncSession, target_date: date | None = None) -> Digest:
    """Generate a daily digest of top relevant items.

    Pipeline:
    1. Pull a candidate pool ordered by heuristic relevance.
    2. If an LLM provider is configured, re-rank against `preferences.md` and
       keep items the LLM accepts (with a written reason attached).
    3. Render the markdown digest.

    Day boundaries are anchored to UTC to match `fetched_at` storage.
    """
    target = target_date or datetime.now(timezone.utc).date()
    start = datetime.combine(target, datetime.min.time(), tzinfo=timezone.utc)
    end = start + timedelta(days=1)

    pool_size = max(settings.digest_candidate_pool_size, settings.digest_target_size)
    result = await db.execute(
        select(Item, Source.name)
        .join(Source, Item.source_id == Source.id)
        .where(Item.fetched_at >= start, Item.fetched_at < end)
        .order_by(Item.relevance_score.desc(), Item.points.desc().nullslast())
        .limit(pool_size)
    )
    rows: list[tuple[Item, str]] = list(result.all())

    selected = await _apply_llm_rerank(rows)
    selected = selected[: settings.digest_target_size]

    content = _render_digest(target, selected)

    existing = await db.execute(select(Digest).where(Digest.date == target))
    digest = existing.scalar_one_or_none()
    if digest:
        digest.content = content
        digest.item_count = len(selected)
    else:
        digest = Digest(date=target, content=content, item_count=len(selected))
        db.add(digest)

    await db.commit()
    await db.refresh(digest)
    return digest


async def _apply_llm_rerank(
    rows: list[tuple[Item, str]],
) -> list[tuple[Item, str, str | None]]:
    """Return (item, source_name, reason) tuples. Reason is None when LLM is off."""
    provider_name = settings.digest_llm_provider.strip().lower()
    api_key = settings.digest_llm_api_key.strip()
    if not provider_name or not api_key or not rows:
        return [(item, source, None) for item, source in rows]

    try:
        provider = Provider(provider_name)
    except ValueError:
        logger.warning("Unknown digest_llm_provider=%r — skipping re-rank", provider_name)
        return [(item, source, None) for item, source in rows]

    candidates = [
        CandidateItem(id=item.id, title=item.title, source=source, summary=item.summary)
        for item, source in rows
    ]

    try:
        verdicts = await rerank_candidates(
            candidates,
            load_preferences_cached(),
            provider=provider,
            api_key=api_key,
        )
    except Exception:
        logger.exception("LLM re-rank failed — falling back to heuristic order")
        return [(item, source, None) for item, source in rows]

    verdict_by_id = {v.item_id: v for v in verdicts}
    kept: list[tuple[Item, str, str | None]] = []
    for item, source in rows:
        v = verdict_by_id.get(item.id)
        if v is None or not v.kept:
            _persist_verdict(item, v)
            continue
        _persist_verdict(item, v)
        kept.append((item, source, v.reason))
    return kept


def _persist_verdict(item: Item, verdict: FilterVerdict | None) -> None:
    if verdict is None:
        return
    meta = json.loads(item.metadata_json) if item.metadata_json else {}
    if not isinstance(meta, dict):
        meta = {}
    meta["llm_kept"] = verdict.kept
    meta["llm_reason"] = verdict.reason
    item.metadata_json = json.dumps(meta)


def _render_digest(target: date, selected: list[tuple[Item, str, str | None]]) -> str:
    sections: list[str] = [f"# AI News Digest — {target.isoformat()}\n"]
    if not selected:
        sections.append("No items collected today.\n")
        return "\n".join(sections)

    for i, (item, source_name, reason) in enumerate(selected, 1):
        score_pct = f"{item.relevance_score * 100:.0f}%"
        points_str = f" | {item.points} pts" if item.points else ""
        block = (
            f"{i}. **[{item.title}]({item.url})**\n"
            f"   Source: {source_name}{points_str} | Relevance: {score_pct}\n"
            f"   {item.summary or ''}\n"
        )
        if reason:
            block += f"   _Why: {reason}_\n"
        sections.append(block)
    return "\n".join(sections)
