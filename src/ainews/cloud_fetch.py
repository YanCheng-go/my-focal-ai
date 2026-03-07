"""Cloud-oriented fetch + score pipeline.

Used by GitHub Actions. Fetches feeds (no Twitter), scores with Claude API,
and stores results in the local SQLite DB for export.
"""

import logging

from ainews.config import Settings, load_principles
from ainews.ingest.feeds import build_feed_urls, fetch_feed
from ainews.scoring.claude_scorer import score_batch_claude
from ainews.storage.db import (
    get_db,
    get_unscored_items,
    ingest_items,
    mark_youtube_shorts_duplicates,
    upsert_item,
)

logger = logging.getLogger(__name__)


async def cloud_fetch_and_score():
    """Fetch RSS/Atom feeds and score with Claude API. No Twitter, no Ollama."""
    settings = Settings()
    conn = get_db(settings.db_path)

    try:
        from ainews.config import load_sources

        sources_config = load_sources(settings.config_dir)
        feeds = build_feed_urls(sources_config)

        total_new = 0
        for feed_meta in feeds:
            source_key = feed_meta["source_name"]
            try:
                items = await fetch_feed(**feed_meta)
                new_count = ingest_items(conn, source_key, items)
                if new_count > 0:
                    skipped = len(items) - new_count
                    logger.info(
                        f"Fetched {new_count} new items from {source_key} ({skipped} skipped)"
                    )
                total_new += new_count
            except Exception:
                logger.exception(f"Failed to fetch {source_key}")

        dupes = mark_youtube_shorts_duplicates(conn)
        if dupes:
            logger.info(f"Marked {dupes} YouTube Shorts as duplicates")

        # Score with Claude API
        unscored = get_unscored_items(conn, limit=30)
        if unscored:
            principles = load_principles(settings.config_dir)
            scored = await score_batch_claude(unscored, principles)
            for item, _ in scored:
                upsert_item(conn, item)
            conn.commit()
            logger.info(f"Scored {len(scored)} items with Claude API")

        logger.info(f"Cloud fetch complete: {total_new} new items from {len(feeds)} feeds")
        return total_new
    finally:
        conn.close()
