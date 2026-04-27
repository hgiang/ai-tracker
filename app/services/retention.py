import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.item import Item

logger = logging.getLogger(__name__)


async def cleanup_expired(db: AsyncSession) -> int:
    """Delete items older than retention_days. Returns count deleted."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.retention_days)
    result = await db.execute(delete(Item).where(Item.fetched_at < cutoff))
    await db.commit()
    count = result.rowcount
    logger.info("Cleaned up %d expired items (older than %s)", count, cutoff.date())
    return count
