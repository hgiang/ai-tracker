import json
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session, get_db
from app.models.source import Source
from app.schemas.source import SourceConfigPatch, SourceCreate, SourceOut, SyncResult
from app.services.ingestion import sync_source

router = APIRouter(prefix="/sources", tags=["sources"])


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:50]


async def _get_source_or_404(db: AsyncSession, slug: str) -> Source:
    result = await db.execute(select(Source).where(Source.slug == slug))
    source = result.scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail=f"Source '{slug}' not found")
    return source


@router.get("", response_model=list[SourceOut])
async def list_sources(db: AsyncSession = Depends(get_db)) -> list[Source]:
    result = await db.execute(select(Source).order_by(Source.name))
    return list(result.scalars().all())


@router.post("", response_model=SourceOut, status_code=201)
async def create_source(
    body: SourceCreate, db: AsyncSession = Depends(get_db)
) -> Source:
    slug = _slugify(body.name)

    existing = await db.execute(select(Source).where(Source.slug == slug))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail=f"Source '{slug}' already exists")

    source = Source(
        name=body.name,
        slug=slug,
        adapter_type=body.adapter_type,
        url=body.url,
        enabled=True,
        config_json=json.dumps(body.config) if body.config else None,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


@router.patch("/{slug}/config", response_model=SourceOut)
async def patch_source_config(
    slug: str, body: SourceConfigPatch, db: AsyncSession = Depends(get_db)
) -> Source:
    source = await _get_source_or_404(db, slug)

    existing = json.loads(source.config_json) if source.config_json else {}
    merged = {**existing, **body.config}
    source.config_json = json.dumps(merged)
    await db.commit()
    await db.refresh(source)
    return source


@router.delete("/{slug}", status_code=200)
async def delete_source(
    slug: str, db: AsyncSession = Depends(get_db)
) -> dict:
    source = await _get_source_or_404(db, slug)
    await db.delete(source)
    await db.commit()
    return {"deleted": slug}


@router.post("/sync", response_model=list[SyncResult])
async def sync_all() -> list[SyncResult]:
    async with async_session() as db:
        result = await db.execute(
            select(Source.id, Source.slug).where(Source.enabled.is_(True))
        )
        sources = list(result.all())

    # Serial, not parallel: concurrent syncs race on cross-source dedup
    # (e.g. arxiv-csai / arxiv-cscl share papers, Reddit subs share titles).
    # Each sync loads duplicate_state before the others commit, so both
    # insert the same canonical_url. Canonical_url has no UNIQUE constraint
    # because convergence logic wants app-level control. Serialising the
    # write phase is the surgical fix.
    results: list[SyncResult] = []
    for source_id, slug in sources:
        try:
            results.append(await _sync_source_by_id(source_id))
        except Exception as exc:
            results.append(
                SyncResult(source=slug, fetched=0, new=0, duplicates=0, error=str(exc))
            )
    return results


@router.post("/sync/{slug}", response_model=SyncResult)
async def sync_one(slug: str, db: AsyncSession = Depends(get_db)) -> SyncResult:
    source = await _get_source_or_404(db, slug)
    return await sync_source(db, source)


async def _sync_source_by_id(source_id: int) -> SyncResult:
    async with async_session() as db:
        result = await db.execute(select(Source).where(Source.id == source_id))
        source = result.scalar_one_or_none()
        if source is None:
            raise RuntimeError(f"Source id={source_id} disappeared during sync")
        return await sync_source(db, source)
