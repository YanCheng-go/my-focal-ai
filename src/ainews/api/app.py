"""FastAPI app — serves both JSON API and web dashboard."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

from ainews.api.admin import _api as admin_api_router
from ainews.api.admin import router as admin_router
from ainews.config import Settings, load_principles, load_sources
from ainews.export import HIDDEN_SOURCE_TYPES, HIDDEN_SOURCES
from ainews.storage.db import get_backend

logger = logging.getLogger(__name__)

settings = Settings()
templates = Jinja2Templates(directory=str(settings.config_dir.parent / "templates"))


def _backend():
    return get_backend(settings.db_path)


async def _fetch_and_score():
    """Background job: fetch feeds then score new items."""
    from ainews.ingest.runner import run_ingestion
    from ainews.scoring.scorer import score_batch

    backend = _backend()
    try:
        await run_ingestion(backend, settings.config_dir)
        if settings.scoring:
            unscored = backend.get_unscored_items(limit=30)
            if unscored:
                principles = load_principles(settings.config_dir)
                scored = await score_batch(
                    unscored, principles, settings.ollama_base_url, settings.ollama_model
                )
                for item, _ in scored:
                    backend.upsert_item(item)
                backend.commit()
        else:
            logger.info("Scoring disabled (AINEWS_SCORING=false)")
    finally:
        backend.close()


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
    since = datetime.now() - timedelta(hours=since_hours) if since_hours else None
    with _backend() as backend:
        items = backend.get_items(
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
        total = backend.count_items(
            min_score=min_score,
            source_type=source_type,
            tier=tier,
            tag=tag,
            search=search,
            since=since,
        )
    return {
        "items": [item.model_dump(mode="json") for item in items],
        "count": len(items),
        "total": total,
    }


@app.get("/api/digest")
def api_digest(hours: int = 24, min_score: float = 0.6):
    """Get a daily digest — top items from the last N hours."""
    since = datetime.now() - timedelta(hours=hours)
    with _backend() as backend:
        items = backend.get_items(limit=20, min_score=min_score, since=since)
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
def api_badge_counts(
    since_dashboard: str | None = None,
    since_trends: str | None = None,
    since_ccc: str | None = None,
    since: str | None = None,
):
    """Count new items per category since per-page timestamps (for notification badges).

    Accepts per-page timestamps (since_dashboard, since_trends, since_ccc).
    Falls back to ``since`` for any missing per-page value.
    """

    def _parse(val: str | None) -> datetime | None:
        if not val:
            return None
        try:
            return datetime.fromisoformat(val)
        except ValueError:
            return None

    fallback_dt = _parse(since)
    dash_dt = _parse(since_dashboard) or fallback_dt
    trend_dt = _parse(since_trends) or fallback_dt
    ccc_dt = _parse(since_ccc) or fallback_dt

    with _backend() as backend:
        dashboard_count = (
            backend.count_items(
                since=dash_dt,
                exclude_source_types=HIDDEN_SOURCE_TYPES,
                exclude_sources=HIDDEN_SOURCES,
            )
            if dash_dt
            else 0
        )
        trends_count = (
            backend.count_items(
                since=trend_dt,
                source_types=["github_trending", "github_trending_history"],
            )
            if trend_dt
            else 0
        )
        ccc_count = 0
        if ccc_dt:
            for src in HIDDEN_SOURCES:
                ccc_count += backend.count_items(since=ccc_dt, source_name=src)
    return {"dashboard": dashboard_count, "trends": trends_count, "ccc": ccc_count}


# === Web Dashboard ===

PER_PAGE = 30


def _get_last_seen(request: Request, page: str) -> datetime | None:
    """Read the last-seen cookie for a page."""
    val = request.cookies.get(f"ainews_last_seen_{page}")
    if not val:
        return None
    try:
        return datetime.fromisoformat(val)
    except ValueError:
        return None


def _set_last_seen(response: Response, page: str) -> None:
    """Set the last-seen cookie for a page to now."""
    response.set_cookie(
        f"ainews_last_seen_{page}",
        datetime.now().isoformat(),  # naive local time, matches fetched_at
        max_age=365 * 24 * 3600,
        samesite="lax",
    )


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
    last_seen = _get_last_seen(request, "dashboard")
    offset = (page - 1) * PER_PAGE
    # Hide dedicated-page sources from the main feed unless explicitly searched/filtered
    has_filter = search or tag or source_type
    filter_kwargs = dict(
        source_type=source_type,
        tier=tier,
        tag=tag,
        min_score=min_score,
        search=search,
        exclude_sources=None if has_filter else HIDDEN_SOURCES,
        exclude_source_types=None if has_filter else HIDDEN_SOURCE_TYPES,
    )
    with _backend() as backend:
        items = backend.get_items(limit=PER_PAGE, offset=offset, order_by=order_by, **filter_kwargs)
        total = backend.count_items(**filter_kwargs)
        all_tags = backend.get_all_tags()
        new_counts: dict[str, int] = {}
        total_new = 0
        if last_seen:
            new_counts = backend.count_items_by_source_type(
                since=last_seen,
                exclude_sources=HIDDEN_SOURCES,
                exclude_source_types=HIDDEN_SOURCE_TYPES,
            )
            total_new = sum(new_counts.values())
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    response = templates.TemplateResponse(
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
            "last_seen_cutoff": last_seen,
            "new_counts_by_type": new_counts,
            "total_new": total_new,
        },
    )
    _set_last_seen(response, "dashboard")
    return response


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
        offset = (page - 1) * PER_PAGE
        with _backend() as backend:
            items = backend.get_items(limit=PER_PAGE, offset=offset, source_type=source_type)
            total = backend.count_items(source_type=source_type)
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
    last_seen = _get_last_seen(request, "trends")
    offset = (page - 1) * PER_PAGE
    source_type = "github_trending_history" if tab == "history" else "github_trending"
    with _backend() as backend:
        items = backend.get_items(
            limit=PER_PAGE, offset=offset, source_type=source_type, order_by="score"
        )
        total = backend.count_items(source_type=source_type)
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    response = templates.TemplateResponse(
        "trends.html",
        {
            "request": request,
            "items": items,
            "tab": tab,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "last_seen_cutoff": last_seen,
        },
    )
    _set_last_seen(response, "trends")
    return response


@app.get("/about", response_class=HTMLResponse)
def about(request: Request):
    return templates.TemplateResponse("about.html", {"request": request})


@app.get("/ccc", response_class=HTMLResponse)
def ccc(request: Request, page: int = 1):
    last_seen = _get_last_seen(request, "ccc")
    offset = (page - 1) * PER_PAGE
    with _backend() as backend:
        items = backend.get_items(limit=PER_PAGE, offset=offset, source_name="Claude Code Releases")
        total = backend.count_items(source_name="Claude Code Releases")
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    response = templates.TemplateResponse(
        "ccc.html",
        {
            "request": request,
            "items": items,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "last_seen_cutoff": last_seen,
        },
    )
    _set_last_seen(response, "ccc")
    return response
