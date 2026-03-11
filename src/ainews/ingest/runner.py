"""Ingestion runner — fetches all configured feeds and stores them."""

import logging

from ainews.config import load_sources
from ainews.ingest.feeds import build_feed_urls, fetch_feed
from ainews.storage.db import ingest_items, mark_youtube_shorts_duplicates

logger = logging.getLogger(__name__)


async def fetch_single_source(conn, sources_config: dict, source_name: str) -> dict:
    """Fetch a single source by name. Returns {"items_fetched": N, "new_items": N}."""
    from ainews.ingest.twitter import fetch_twitter_user, get_twitter_cookies_from_browser
    from ainews.ingest.xiaohongshu import fetch_xhs_user, get_xhs_cookies_from_browser

    # Check Twitter handles
    twitter_users = sources_config.get("sources", {}).get("twitter", [])
    for user in twitter_users:
        handle = user["handle"]
        if source_name.lower() in (handle.lower(), f"@{handle}".lower()):
            cookies = get_twitter_cookies_from_browser()
            if not cookies:
                raise RuntimeError("No Twitter cookies found in Chrome")
            items = await fetch_twitter_user(handle, cookies, tags=user.get("tags", []))
            new_count = ingest_items(conn, f"twitter:@{handle}", items)
            return {"items_fetched": len(items), "new_items": new_count}

    # Check Xiaohongshu users
    xhs_users = sources_config.get("sources", {}).get("xiaohongshu", [])
    for user in xhs_users:
        user_id = user["user_id"]
        name = user.get("name", user_id)
        if source_name.lower() in (name.lower(), user_id.lower()):
            cookies = get_xhs_cookies_from_browser()
            if not cookies:
                raise RuntimeError("No XHS cookies found in Chrome")
            items = await fetch_xhs_user(user_id, cookies, name=name, tags=user.get("tags", []))
            new_count = ingest_items(conn, f"xiaohongshu:{user_id}", items)
            return {"items_fetched": len(items), "new_items": new_count}

    # Check event sources
    from ainews.ingest.events import fetch_anthropic_events, fetch_google_dev_events

    event_sources = sources_config.get("sources", {}).get("events", [])
    for src in event_sources:
        name = src.get("name", "")
        if source_name.lower() in name.lower():
            scraper = src.get("scraper", "")
            tags = src.get("tags", [])
            if scraper == "anthropic":
                items = await fetch_anthropic_events(tags=tags)
            elif scraper == "google_dev":
                items = await fetch_google_dev_events(tags=tags)
            else:
                raise ValueError(f"Unknown event scraper: {scraper}")
            new_count = ingest_items(conn, name, items)
            return {"items_fetched": len(items), "new_items": new_count}

    # Check GitHub trending
    trending_entries = sources_config.get("sources", {}).get("github_trending", [])
    if trending_entries and "github" in source_name.lower() and "trend" in source_name.lower():
        from ainews.ingest.github_trending import (
            fetch_github_trending,
            fetch_github_trending_history,
        )

        tags = trending_entries[0].get("tags", ["github", "trending", "open-source"])
        total_fetched = 0
        total_new = 0
        items = await fetch_github_trending(tags=tags)
        total_fetched += len(items)
        total_new += ingest_items(conn, "GitHub Trending", items)
        history_items = await fetch_github_trending_history(tags=tags)
        total_fetched += len(history_items)
        total_new += ingest_items(conn, "GitHub Trending History", history_items)
        return {"items_fetched": total_fetched, "new_items": total_new}

    # Check all feed sources
    feeds = build_feed_urls(sources_config)
    matched = [f for f in feeds if source_name.lower() in f["source_name"].lower()]

    if not matched:
        raise ValueError(f"No source found matching '{source_name}'")

    total_fetched = 0
    total_new = 0
    for feed_meta in matched:
        items = await fetch_feed(**feed_meta)
        new_count = ingest_items(conn, feed_meta["source_name"], items)
        total_fetched += len(items)
        total_new += new_count

    return {"items_fetched": total_fetched, "new_items": total_new}


async def run_ingestion(conn, config_dir=None):
    """Fetch all feeds and store only new items."""
    from ainews.backfill import sync_source_metadata
    from ainews.ingest.events import run_events_ingestion
    from ainews.ingest.github_trending import run_github_trending_ingestion
    from ainews.ingest.twitter import run_twitter_ingestion
    from ainews.ingest.xiaohongshu import run_xhs_ingestion

    sources_config = load_sources(config_dir)

    # RSS/Atom feeds (YouTube, arXiv, blogs, RSSHub routes)
    feeds = build_feed_urls(sources_config)
    total_new = 0
    for feed_meta in feeds:
        source_key = feed_meta["source_name"]
        try:
            items = await fetch_feed(**feed_meta)
            new_count = ingest_items(conn, source_key, items)
            if new_count > 0:
                skipped = len(items) - new_count
                logger.info(f"Fetched {new_count} new items from {source_key} ({skipped} skipped)")
            total_new += new_count
        except Exception:
            logger.exception(f"Failed to fetch {source_key}")

    # Twitter (direct scraping via Chrome cookies)
    try:
        twitter_count = await run_twitter_ingestion(conn, sources_config)
        total_new += twitter_count
    except Exception:
        logger.exception("Twitter ingestion failed")

    # Xiaohongshu (direct scraping via Chrome cookies)
    try:
        xhs_count = await run_xhs_ingestion(conn, sources_config)
        total_new += xhs_count
    except Exception:
        logger.exception("Xiaohongshu ingestion failed")

    # Events (web scraping — Anthropic, Google, etc.)
    try:
        events_count = await run_events_ingestion(conn, sources_config)
        total_new += events_count
    except Exception:
        logger.exception("Events ingestion failed")

    # GitHub trending (trendshift.io scraping)
    try:
        trending_count = await run_github_trending_ingestion(conn, sources_config)
        total_new += trending_count
    except Exception:
        logger.exception("GitHub trending ingestion failed")

    # Sync tags and source_type from config to existing items (skips if unchanged)
    try:
        sync_source_metadata(conn, sources_config, config_dir=config_dir)
    except Exception:
        logger.exception("Metadata sync failed")

    # Mark YouTube Shorts as duplicates of their full video counterpart
    dupes = mark_youtube_shorts_duplicates(conn)
    if dupes:
        logger.info(f"Marked {dupes} YouTube Shorts as duplicates")

    logger.info(
        f"Ingestion complete: {total_new} new items from "
        f"{len(feeds)} feeds + twitter + xhs + events + github_trending"
    )
    return total_new
