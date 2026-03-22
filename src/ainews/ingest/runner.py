"""Ingestion runner — fetches all configured feeds and stores them."""

import logging
from datetime import datetime, timedelta, timezone

from ainews.config import Settings, load_sources
from ainews.ingest.feeds import build_feed_urls, fetch_feed

logger = logging.getLogger(__name__)


async def fetch_single_source(backend, sources_config: dict, source_name: str) -> dict:
    """Fetch a single source by name. Returns {"items_fetched": N, "new_items": N}."""
    from ainews.ingest.twitter import fetch_twitter_user, get_twitter_cookies_from_browser

    name_lower = source_name.lower()
    sources = sources_config.get("sources", {})

    # Check Twitter handles
    twitter_users = sources.get("twitter", [])
    for user in twitter_users:
        handle = user["handle"]
        if name_lower in (handle.lower(), f"@{handle}".lower()):
            cookies = get_twitter_cookies_from_browser()
            if not cookies:
                raise RuntimeError("No Twitter cookies found in Chrome")
            items = await fetch_twitter_user(handle, cookies, tags=user.get("tags", []))
            new_count = backend.ingest_items(f"twitter:@{handle}", items)
            return {"items_fetched": len(items), "new_items": new_count}

    # Check event sources
    from ainews.ingest.events import fetch_anthropic_events, fetch_google_dev_events

    event_sources = sources.get("events", [])
    for src in event_sources:
        name = src.get("name", "")
        if name_lower in name.lower():
            scraper = src.get("scraper", "")
            tags = src.get("tags", [])
            if scraper == "anthropic":
                items = await fetch_anthropic_events(tags=tags)
            elif scraper == "google_dev":
                items = await fetch_google_dev_events(tags=tags)
            else:
                raise ValueError(f"Unknown event scraper: {scraper}")
            new_count = backend.ingest_items(name, items)
            return {"items_fetched": len(items), "new_items": new_count}

    # Check AI Templates trending
    aitmpl_entries = sources.get("aitmpl_trending", [])
    is_aitmpl = "aitmpl" in name_lower or ("template" in name_lower and "trend" in name_lower)
    if aitmpl_entries and is_aitmpl:
        from ainews.ingest.aitmpl_trending import (
            _COMPONENT_TYPES,
            fetch_aitmpl_trending,
        )
        from ainews.ingest.aitmpl_trending import (
            DEFAULT_TAGS as AITMPL_DEFAULT_TAGS,
        )

        tags = aitmpl_entries[0].get("tags", AITMPL_DEFAULT_TAGS)
        items = await fetch_aitmpl_trending(tags=tags)
        backend.delete_source_content("AI Templates Trending")
        for ct in _COMPONENT_TYPES:
            backend.delete_source_content(f"AI Templates Trending ({ct})")
        new_count = backend.ingest_items("AI Templates Trending", items)
        return {"items_fetched": len(items), "new_items": new_count}

    # Check skills.sh trending
    skillssh_entries = sources.get("skillssh_trending", [])
    is_skillssh = "skills.sh" in name_lower or "skillssh" in name_lower
    if skillssh_entries and is_skillssh:
        from ainews.ingest.skillssh_trending import (
            _ALL_PAGE_KEYS,
            fetch_skillssh_trending,
        )
        from ainews.ingest.skillssh_trending import (
            DEFAULT_TAGS as SKILLSSH_DEFAULT_TAGS,
        )

        tags = skillssh_entries[0].get("tags", SKILLSSH_DEFAULT_TAGS)
        items = await fetch_skillssh_trending(tags=tags)
        for pk in _ALL_PAGE_KEYS:
            backend.delete_source_content(f"skills.sh ({pk})")
        new_count = backend.ingest_items("skills.sh (all)", items)
        return {"items_fetched": len(items), "new_items": new_count}

    # Check GitHub trending
    trending_entries = sources.get("github_trending", [])
    if trending_entries and "github" in name_lower and "trend" in name_lower:
        from ainews.ingest.github_trending import (
            fetch_github_trending,
            fetch_github_trending_history,
        )

        tags = trending_entries[0].get("tags", ["github", "trending", "open-source"])
        items = await fetch_github_trending(tags=tags)
        history_items = await fetch_github_trending_history(tags=tags)
        # Clear both before inserting to avoid UNIQUE(url) conflicts
        if items:
            backend.delete_source_content("GitHub Trending")
        if history_items:
            backend.delete_source_content("GitHub Trending History")
        total_fetched = len(items) + len(history_items)
        total_new = backend.ingest_items("GitHub Trending", items)
        total_new += backend.ingest_items("GitHub Trending History", history_items)
        return {"items_fetched": total_fetched, "new_items": total_new}

    # Check all feed sources
    feeds = build_feed_urls(sources_config)
    matched = [f for f in feeds if name_lower in f["source_name"].lower()]

    if not matched:
        raise ValueError(f"No source found matching '{source_name}'")

    total_fetched = 0
    total_new = 0
    for feed_meta in matched:
        items = await fetch_feed(**feed_meta)
        new_count = backend.ingest_items(feed_meta["source_name"], items)
        total_fetched += len(items)
        total_new += new_count

    return {"items_fetched": total_fetched, "new_items": total_new}


async def run_ingestion(backend, config_dir=None, sources_config=None):
    """Fetch all feeds and store only new items."""
    from ainews.backfill import sync_source_metadata
    from ainews.ingest.aitmpl_trending import run_aitmpl_trending_ingestion
    from ainews.ingest.events import run_events_ingestion
    from ainews.ingest.github_trending import run_github_trending_ingestion
    from ainews.ingest.skillssh_trending import run_skillssh_trending_ingestion
    from ainews.ingest.twitter import run_twitter_ingestion

    sources_config = sources_config or load_sources(config_dir)

    # RSS/Atom feeds (YouTube, arXiv, blogs, RSSHub routes)
    feeds = build_feed_urls(sources_config)
    total_new = 0
    for feed_meta in feeds:
        source_key = feed_meta["source_name"]
        try:
            items = await fetch_feed(**feed_meta)
            new_count = backend.ingest_items(source_key, items)
            if new_count > 0:
                skipped = len(items) - new_count
                logger.info(f"Fetched {new_count} new items from {source_key} ({skipped} skipped)")
            total_new += new_count
        except Exception:
            logger.exception(f"Failed to fetch {source_key}")

    # Twitter (direct scraping via Chrome cookies)
    try:
        twitter_count = await run_twitter_ingestion(backend, sources_config)
        total_new += twitter_count
    except Exception:
        logger.exception("Twitter ingestion failed")

    # Events (web scraping — Anthropic, Google, etc.)
    try:
        events_count = await run_events_ingestion(backend, sources_config)
        total_new += events_count
    except Exception:
        logger.exception("Events ingestion failed")

    # GitHub trending (trendshift.io scraping)
    try:
        trending_count = await run_github_trending_ingestion(backend, sources_config)
        total_new += trending_count
    except Exception:
        logger.exception("GitHub trending ingestion failed")

    # AI Templates trending (aitmpl.com)
    try:
        aitmpl_count = await run_aitmpl_trending_ingestion(backend, sources_config)
        total_new += aitmpl_count
    except Exception:
        logger.exception("AI Templates trending ingestion failed")

    # skills.sh trending
    try:
        skillssh_count = await run_skillssh_trending_ingestion(backend, sources_config)
        total_new += skillssh_count
    except Exception:
        logger.exception("skills.sh trending ingestion failed")

    # Sync tags and source_type from config to existing items (skips if unchanged)
    try:
        sync_source_metadata(backend, sources_config, config_dir=config_dir)
    except Exception:
        logger.exception("Metadata sync failed")

    # Mark YouTube Shorts as duplicates of their full video counterpart
    dupes = backend.mark_youtube_shorts_duplicates()
    if dupes:
        logger.info(f"Marked {dupes} YouTube Shorts as duplicates")

    # Prune past events/luma items after configured retention period
    settings = Settings()
    if settings.event_retention_days > 0:
        event_cutoff = datetime.now(timezone.utc) - timedelta(days=settings.event_retention_days)
        past_events = backend.delete_past_events(event_cutoff)
        if past_events:
            days = settings.event_retention_days
            logger.info(f"Pruned {past_events} past events older than {days} days")

    # Prune items older than retention period
    if settings.retention_days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.retention_days)
        deleted = backend.delete_old_items(cutoff)
        if deleted:
            logger.info(f"Pruned {deleted} items older than {settings.retention_days} days")

    logger.info(
        f"Ingestion complete: {total_new} new items from "
        f"{len(feeds)} feeds + twitter + events + github_trending"
    )
    return total_new
