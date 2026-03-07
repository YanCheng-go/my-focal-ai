"""Ingestion runner — fetches all configured feeds and stores them."""

import logging
import sqlite3

from ainews.config import load_sources
from ainews.ingest.feeds import build_feed_urls, fetch_feed
from ainews.ingest.twitter import run_twitter_ingestion
from ainews.storage.db import upsert_item

logger = logging.getLogger(__name__)


async def run_ingestion(conn: sqlite3.Connection, config_dir=None):
    """Fetch all feeds and store new items."""
    sources_config = load_sources(config_dir)

    # RSS/Atom feeds (YouTube, arXiv, blogs, RSSHub routes)
    feeds = build_feed_urls(sources_config)
    total_new = 0
    for feed_meta in feeds:
        try:
            items = await fetch_feed(**feed_meta)
            for item in items:
                upsert_item(conn, item)
            total_new += len(items)
            logger.info(f"Fetched {len(items)} items from {feed_meta['source_name']}")
        except Exception:
            logger.exception(f"Failed to fetch {feed_meta['source_name']}")

    # Twitter via twscrape (direct scraping, no API keys)
    try:
        twitter_count = await run_twitter_ingestion(conn, sources_config)
        total_new += twitter_count
    except Exception:
        logger.exception("Twitter ingestion failed")

    logger.info(f"Ingestion complete: {total_new} items from {len(feeds)} feeds + twitter")
    return total_new
