"""Ingestion runner — fetches all configured feeds and stores them."""

import logging
import sqlite3

from ainews.config import load_sources
from ainews.ingest.feeds import build_feed_urls, fetch_feed
from ainews.ingest.twitter import run_twitter_ingestion
from ainews.ingest.xiaohongshu import run_xhs_ingestion
from ainews.storage.db import ingest_items, mark_youtube_shorts_duplicates

logger = logging.getLogger(__name__)


async def fetch_single_source(
    conn: sqlite3.Connection, sources_config: dict, source_name: str
) -> dict:
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


async def run_ingestion(conn: sqlite3.Connection, config_dir=None):
    """Fetch all feeds and store only new items."""
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

    # Mark YouTube Shorts as duplicates of their full video counterpart
    dupes = mark_youtube_shorts_duplicates(conn)
    if dupes:
        logger.info(f"Marked {dupes} YouTube Shorts as duplicates")

    logger.info(
        f"Ingestion complete: {total_new} new items from {len(feeds)} feeds + twitter + xhs"
    )
    return total_new
