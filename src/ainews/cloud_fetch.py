"""Cloud-oriented fetch + score pipeline.

Used by GitHub Actions. Fetches feeds (no Twitter/XHS) and optionally scores
with Claude API if ANTHROPIC_API_KEY is set.
"""

import logging
import os

from ainews.config import Settings, load_principles
from ainews.ingest.runner import run_ingestion
from ainews.storage.db import get_db, get_unscored_items, upsert_item

logger = logging.getLogger(__name__)


async def cloud_fetch_and_score():
    """Fetch RSS/Atom feeds. Scores with Claude API if ANTHROPIC_API_KEY is set."""
    settings = Settings()
    conn = get_db(settings.db_path, settings.turso_url, settings.turso_auth_token)

    try:
        # Reuse the standard ingestion pipeline (Twitter/XHS gracefully skip
        # when Chrome cookies are unavailable, i.e. in CI)
        total_new = await run_ingestion(conn, settings.config_dir)

        # Score with Claude API if key is available
        if os.environ.get("ANTHROPIC_API_KEY"):
            from ainews.scoring.claude_scorer import score_batch_claude

            unscored = get_unscored_items(conn, limit=30)
            if unscored:
                principles = load_principles(settings.config_dir)
                scored = await score_batch_claude(unscored, principles)
                for item, _ in scored:
                    upsert_item(conn, item)
                conn.commit()
                logger.info(f"Scored {len(scored)} items with Claude API")
        else:
            logger.info("ANTHROPIC_API_KEY not set — skipping scoring")

        logger.info(f"Cloud fetch complete: {total_new} new items")
        return total_new
    finally:
        conn.close()
