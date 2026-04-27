"""One-shot cleanup for duplicate items created by the cross-source race
in `sync_all` (see `app/routes/sources.py`).

Strategy: for each canonical_url appearing in >1 row, keep the row with the
lowest id and delete the rest. Idempotent — re-running is a no-op.

Usage:
    uv run python -m scripts.dedupe_items           # report + delete
    uv run python -m scripts.dedupe_items --dry-run  # report only
"""
import argparse
import asyncio
import logging

from sqlalchemy import delete, func, select

from app.database import async_session
from app.models.item import Item

logger = logging.getLogger(__name__)


async def _find_duplicate_groups(session) -> list[tuple[str, int]]:
    """Return [(canonical_url, count), ...] for urls with >1 row."""
    stmt = (
        select(Item.canonical_url, func.count(Item.id).label("n"))
        .group_by(Item.canonical_url)
        .having(func.count(Item.id) > 1)
    )
    return list((await session.execute(stmt)).all())


async def _ids_to_delete(session, canonical_url: str) -> list[int]:
    """Return all Item ids for this url EXCEPT the lowest (kept) id."""
    result = await session.execute(
        select(Item.id).where(Item.canonical_url == canonical_url).order_by(Item.id)
    )
    ids = [row[0] for row in result.all()]
    return ids[1:]  # keep ids[0], delete the rest


async def dedupe(dry_run: bool) -> tuple[int, int]:
    """Return (groups_found, rows_deleted)."""
    async with async_session() as session:
        groups = await _find_duplicate_groups(session)
        if not groups:
            return 0, 0

        total_to_delete = 0
        all_ids: list[int] = []
        for canonical_url, count in groups:
            delete_ids = await _ids_to_delete(session, canonical_url)
            total_to_delete += len(delete_ids)
            all_ids.extend(delete_ids)
            logger.info(
                "%s (%s rows) → delete %s, keep %s",
                canonical_url,
                count,
                len(delete_ids),
                count - len(delete_ids),
            )

        if dry_run:
            logger.info("DRY RUN — no rows deleted")
            return len(groups), total_to_delete

        if all_ids:
            await session.execute(delete(Item).where(Item.id.in_(all_ids)))
            await session.commit()

        return len(groups), total_to_delete


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report without deleting")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    groups, deleted = asyncio.run(dedupe(dry_run=args.dry_run))
    verb = "would delete" if args.dry_run else "deleted"
    logger.info("Done: %s duplicate group(s), %s rows %s", groups, deleted, verb)


if __name__ == "__main__":
    main()
