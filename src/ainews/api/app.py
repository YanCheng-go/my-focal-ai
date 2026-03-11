"""FastAPI app — serves both JSON API and web dashboard."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ainews.api.admin import _api as admin_api_router
from ainews.api.admin import router as admin_router
from ainews.config import Settings, load_principles, load_sources
from ainews.storage.db import (
    count_items,
    get_all_tags,
    get_db,
    get_items,
    get_unscored_items,
    upsert_item,
)

logger = logging.getLogger(__name__)

settings = Settings()
templates = Jinja2Templates(directory=str(settings.config_dir.parent / "templates"))


def _conn():
    return get_db(settings.db_path)


async def _fetch_and_score():
    """Background job: fetch feeds then score new items."""
    from ainews.ingest.runner import run_ingestion
    from ainews.scoring.scorer import score_batch

    conn = _conn()
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
        else:
            logger.info("Scoring disabled (AINEWS_SCORING=false)")
    finally:
        conn.close()


def _create_app(*, with_scheduler: bool = True) -> FastAPI:
    """Create the FastAPI app. Scheduler is disabled on Vercel."""
    lifespan_ctx = None
    if with_scheduler:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            scheduler = AsyncIOScheduler()
            scheduler.add_job(
                _fetch_and_score,
                "interval",
                minutes=settings.fetch_interval_minutes,
                next_run_time=datetime.now(),
            )
            scheduler.start()
            yield
            scheduler.shutdown()

        lifespan_ctx = lifespan

    return FastAPI(title="MyFocalAI", version="0.3.0", lifespan=lifespan_ctx)


# Detect Vercel environment — no scheduler, no static mount
_on_vercel = bool(os.environ.get("VERCEL"))
app = _create_app(with_scheduler=not _on_vercel)
app.include_router(admin_router)
app.include_router(admin_api_router)

if not _on_vercel:
    from fastapi.staticfiles import StaticFiles

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
    conn = _conn()
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
    conn = _conn()
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
    """Manually trigger a fetch + score cycle (local mode only)."""
    asyncio.create_task(_fetch_and_score())
    return {"status": "started"}


@app.get("/api/badge-counts")
def api_badge_counts(since: str | None = None):
    """Count new items per category since a given timestamp (for notification badges)."""
    if not since:
        return {"dashboard": 0, "trends": 0, "ccc": 0}
    try:
        since_dt = datetime.fromisoformat(since)
    except ValueError:
        return {"dashboard": 0, "trends": 0, "ccc": 0}
    conn = _conn()
    dashboard_count = count_items(
        conn,
        since=since_dt,
        exclude_source_types=["events", "luma", "github_trending", "github_trending_history"],
        exclude_sources=["Claude Code Releases"],
    )
    trends_count = count_items(conn, since=since_dt, source_type="github_trending") + count_items(
        conn, since=since_dt, source_type="github_trending_history"
    )
    ccc_count = count_items(conn, since=since_dt, source_name="Claude Code Releases")
    conn.close()
    return {"dashboard": dashboard_count, "trends": trends_count, "ccc": ccc_count}


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
    conn = _conn()
    offset = (page - 1) * PER_PAGE
    # Hide dedicated-page sources from the main feed unless explicitly searched/filtered
    has_filter = search or tag or source_type
    filter_kwargs = dict(
        source_type=source_type,
        tier=tier,
        tag=tag,
        min_score=min_score,
        search=search,
        exclude_sources=None if has_filter else ["Claude Code Releases"],
        exclude_source_types=None
        if has_filter
        else ["events", "luma", "github_trending", "github_trending_history"],
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
            "show_scores": settings.show_scores,
        },
    )


@app.get("/leaderboard", response_class=HTMLResponse)
def leaderboard(request: Request):
    sources_config = load_sources(settings.config_dir)
    leaderboard_links = sources_config.get("sources", {}).get("leaderboard", [])
    return templates.TemplateResponse(
        "leaderboard.html",
        {"request": request, "leaderboard_links": leaderboard_links},
    )


@app.get("/events", response_class=HTMLResponse)
def events(request: Request, tab: str = "calendars", page: int = 1):
    sources_config = load_sources(settings.config_dir)
    event_links = sources_config.get("sources", {}).get("event_links", [])
    items = []
    total = 0
    total_pages = 1
    if tab in ("luma", "tech"):
        source_type = "luma" if tab == "luma" else "events"
        conn = _conn()
        offset = (page - 1) * PER_PAGE
        items = get_items(conn, limit=PER_PAGE, offset=offset, source_type=source_type)
        total = count_items(conn, source_type=source_type)
        conn.close()
        total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    return templates.TemplateResponse(
        "events.html",
        {
            "request": request,
            "event_links": event_links,
            "items": items,
            "tab": tab,
            "page": page,
            "total_pages": total_pages,
            "total": total,
        },
    )


@app.get("/trends", response_class=HTMLResponse)
def trends(request: Request, tab: str = "daily", page: int = 1):
    conn = _conn()
    offset = (page - 1) * PER_PAGE
    source_type = "github_trending_history" if tab == "history" else "github_trending"
    items = get_items(
        conn, limit=PER_PAGE, offset=offset, source_type=source_type, order_by="score"
    )
    total = count_items(conn, source_type=source_type)
    conn.close()
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    return templates.TemplateResponse(
        "trends.html",
        {
            "request": request,
            "items": items,
            "tab": tab,
            "page": page,
            "total_pages": total_pages,
            "total": total,
        },
    )


@app.get("/about", response_class=HTMLResponse)
def about(request: Request):
    return templates.TemplateResponse("about.html", {"request": request})


@app.get("/ccc", response_class=HTMLResponse)
def ccc(request: Request, page: int = 1):
    conn = _conn()
    offset = (page - 1) * PER_PAGE
    items = get_items(conn, limit=PER_PAGE, offset=offset, search="Claude Code Releases")
    total = count_items(conn, search="Claude Code Releases")
    conn.close()
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    return templates.TemplateResponse(
        "ccc.html",
        {
            "request": request,
            "items": items,
            "page": page,
            "total_pages": total_pages,
            "total": total,
        },
    )
