from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.digest import Digest
from app.schemas.digest import DigestOut
from app.services.digest import generate_digest
from app.services.retention import cleanup_expired

router = APIRouter(prefix="/digests", tags=["digests"])


@router.get("/latest", response_model=DigestOut)
async def latest_digest(db: AsyncSession = Depends(get_db)) -> Digest:
    result = await db.execute(select(Digest).order_by(Digest.date.desc()).limit(1))
    digest = result.scalar_one_or_none()
    if digest is None:
        raise HTTPException(status_code=404, detail="No digests yet")
    return digest


@router.post("/generate", response_model=DigestOut)
async def create_digest(
    target_date: date | None = None,
    db: AsyncSession = Depends(get_db),
) -> Digest:
    return await generate_digest(db, target_date)


@router.post("/cleanup")
async def run_cleanup(db: AsyncSession = Depends(get_db)) -> dict[str, int]:
    deleted = await cleanup_expired(db)
    return {"deleted": deleted}
