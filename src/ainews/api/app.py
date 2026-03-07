"""FastAPI app — serves both JSON API and web dashboard."""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ainews.config import Settings, load_principles
from ainews.ingest.runner import run_ingestion
from ainews.scoring.scorer import score_batch
from ainews.storage.db import (
    count_items,
    get_all_tags,
    get_db,
    get_items,
    get_unscored_items,
    upsert_item,
)

settings = Settings()
templates = Jinja2Templates(directory=str(settings.config_dir.parent / "templates"))


async def _fetch_and_score():
    """Background job: fetch feeds then score new items."""
    conn = get_db(settings.db_path)
    try:
        await run_ingestion(conn, settings.config_dir)
        if settings.scoring:
            unscored = get_unscored_items(conn, limit=30)
            if unscored:
                principles = load_principles(settings.config_dir)
                scored = await score_batch(
                    unscored, principles, settings.ollama_base_url, settings.ollama_model
                )
                for item, _ in scored:
                    upsert_item(conn, item)
                conn.commit()
    finally:
        conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _fetch_and_score,
        "interval",
        minutes=settings.fetch_interval_minutes,
        next_run_time=datetime.now(),  # run immediately on startup
    )
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="AI News Filter", version="0.1.0", lifespan=lifespan)
static_dir = str(settings.config_dir.parent / "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


# === JSON API (AI-friendly) ===


@app.get("/api/items")
def api_items(
    limit: int = Query(50, le=200),
    offset: int = 0,
    min_score: float | None = None,
    source_type: str | None = None,
    tier: str | None = None,
    tag: str | None = None,
    search: str | None = None,
    since_hours: int | None = None,
    order_by: str = "date",
):
    """Get scored content items as JSON. Designed for programmatic / AI consumption."""
    conn = get_db(settings.db_path)
    since = datetime.now() - timedelta(hours=since_hours) if since_hours else None
    items = get_items(
        conn,
        limit=limit,
        offset=offset,
        min_score=min_score,
        source_type=source_type,
        tier=tier,
        tag=tag,
        search=search,
        since=since,
        order_by=order_by,
    )
    total = count_items(
        conn,
        min_score=min_score,
        source_type=source_type,
        tier=tier,
        tag=tag,
        search=search,
        since=since,
    )
    conn.close()
    return {
        "items": [item.model_dump(mode="json") for item in items],
        "count": len(items),
        "total": total,
    }


@app.get("/api/digest")
def api_digest(hours: int = 24, min_score: float = 0.6):
    """Get a daily digest — top items from the last N hours."""
    conn = get_db(settings.db_path)
    since = datetime.now() - timedelta(hours=hours)
    items = get_items(conn, limit=20, min_score=min_score, since=since)
    conn.close()
    return {
        "period_hours": hours,
        "min_score": min_score,
        "items": [
            {
                "title": i.title,
                "url": i.url,
                "score": i.score,
                "tier": i.tier,
                "reason": i.score_reason,
                "source": i.source_name,
            }
            for i in items
        ],
    }


@app.post("/api/fetch")
async def api_trigger_fetch():
    """Manually trigger a fetch + score cycle."""
    asyncio.create_task(_fetch_and_score())
    return {"status": "started"}


# === Web Dashboard ===

PER_PAGE = 30


@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    source_type: str | None = None,
    tier: str | None = None,
    tag: str | None = None,
    min_score: float | None = None,
    search: str | None = None,
    order_by: str = "date",
    page: int = 1,
):
    conn = get_db(settings.db_path)
    offset = (page - 1) * PER_PAGE
    filter_kwargs = dict(
        source_type=source_type, tier=tier, tag=tag, min_score=min_score, search=search
    )
    items = get_items(conn, limit=PER_PAGE, offset=offset, order_by=order_by, **filter_kwargs)
    total = count_items(conn, **filter_kwargs)
    all_tags = get_all_tags(conn)
    conn.close()
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "items": items,
            "filters": {
                "source_type": source_type,
                "tier": tier,
                "tag": tag,
                "min_score": min_score,
                "order_by": order_by,
                "search": search,
            },
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "all_tags": all_tags,
        },
    )
