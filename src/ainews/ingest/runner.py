"""Ingestion runner — fetches all configured feeds and stores them."""

import logging
import sqlite3

from ainews.config import load_sources
from ainews.ingest.feeds import build_feed_urls, fetch_feed
from ainews.ingest.twitter import run_twitter_ingestion
from ainews.storage.db import item_exists, set_last_fetched, upsert_item, mark_youtube_shorts_duplicates

logger = logging.getLogger(__name__)


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
            new_count = 0
            for item in items:
                if not item_exists(conn, item.id):
                    upsert_item(conn, item)
                    new_count += 1
            if new_count > 0:
                logger.info(f"Fetched {new_count} new items from {source_key} ({len(items) - new_count} skipped)")
            set_last_fetched(conn, source_key)
            total_new += new_count
        except Exception:
            logger.exception(f"Failed to fetch {source_key}")

    # Twitter (direct scraping via Chrome cookies)
    try:
        twitter_count = await run_twitter_ingestion(conn, sources_config)
        total_new += twitter_count
    except Exception:
        logger.exception("Twitter ingestion failed")

    # Mark YouTube Shorts as duplicates of their full video counterpart
    dupes = mark_youtube_shorts_duplicates(conn)
    if dupes:
        logger.info(f"Marked {dupes} YouTube Shorts as duplicates")

    logger.info(f"Ingestion complete: {total_new} new items from {len(feeds)} feeds + twitter")
    return total_new
