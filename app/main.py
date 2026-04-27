import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.base import close_shared_client
from app.adapters.registry import DEFAULT_SOURCES
from app.database import async_session, engine
from app.models import Base, Source
from app.routes import digests, health, items, paper_tools, sources
from app.services.kimi import close_kimi_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _migrate_item_duration()
    await _seed_default_sources()
    await _migrate_content_types()
    yield
    await close_shared_client()
    await close_kimi_client()
    await engine.dispose()


async def _seed_default_sources() -> None:
    async with async_session() as db:
        result = await db.execute(select(Source))
        existing = {s.slug: s for s in result.scalars().all()}

        for src in DEFAULT_SOURCES:
            config = src.get("config")
            config_json = json.dumps(config) if config else None

            if src["slug"] not in existing:
                db.add(
                    Source(
                        name=src["name"],
                        slug=src["slug"],
                        adapter_type=src["adapter_type"],
                        url=src["url"],
                        config_json=config_json,
                    )
                )
            else:
                source = existing[src["slug"]]
                if source.adapter_type != src["adapter_type"] or source.url != src["url"]:
                    source.adapter_type = src["adapter_type"]
                    source.url = src["url"]
                    source.config_json = config_json

        await db.commit()


async def _migrate_content_types() -> None:
    """Migrate old 'short'/'long' content_type values to new categories."""
    async with async_session() as db:
        result = await db.execute(
            text("SELECT COUNT(*) FROM items WHERE content_type IN ('short', 'long')")
        )
        if result.scalar():
            await db.execute(text("UPDATE items SET content_type = 'news' WHERE content_type = 'short'"))
            await db.execute(text("UPDATE items SET content_type = 'article' WHERE content_type = 'long'"))
            await db.commit()


async def _migrate_item_duration(target_engine: AsyncEngine | None = None) -> None:
    """Backfill the duration column for existing databases created before the field existed."""
    target_engine = target_engine or engine
    async with target_engine.begin() as conn:
        columns = await conn.run_sync(lambda sync_conn: {c["name"] for c in inspect(sync_conn).get_columns("items")})
        if "duration" in columns:
            return
        await conn.execute(text("ALTER TABLE items ADD COLUMN duration VARCHAR(20)"))
        logging.getLogger(__name__).info("Added missing items.duration column")


app = FastAPI(title="AI Tracker", version="0.1.0", lifespan=lifespan)

app.include_router(health.router)
app.include_router(sources.router, prefix="/api")
app.include_router(items.router, prefix="/api")
app.include_router(digests.router, prefix="/api")
app.include_router(paper_tools.router, prefix="/api")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def serve_frontend():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/summary")
async def serve_summary():
    return FileResponse(STATIC_DIR / "summary.html")


@app.get("/notebook")
async def serve_notebook():
    return FileResponse(STATIC_DIR / "notebook.html")
