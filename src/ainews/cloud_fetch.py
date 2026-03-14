"""Cloud-oriented fetch + score pipeline.

Used by GitHub Actions. Fetches feeds (no Twitter/XHS) and optionally scores
with Claude API if ANTHROPIC_API_KEY is set.
"""

import logging
import os

from ainews.config import Settings, load_principles
from ainews.ingest.runner import run_ingestion
from ainews.storage.db import get_backend

logger = logging.getLogger(__name__)


async def _score_with_claude(backend, settings, label: str = "") -> int:
    """Score unscored items with Claude API if ANTHROPIC_API_KEY is set. Returns count."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        if not label:
            logger.info("ANTHROPIC_API_KEY not set — skipping scoring")
        return 0
    from ainews.scoring.claude_scorer import score_batch_claude

    unscored = backend.get_unscored_items(limit=30)
    if not unscored:
        return 0
    principles = load_principles(settings.config_dir)
    scored = await score_batch_claude(unscored, principles)
    for item, _ in scored:
        backend.upsert_item(item)
    backend.commit()
    prefix = f"{label}: " if label else ""
    logger.info(f"{prefix}Scored {len(scored)} items with Claude API")
    return len(scored)


async def cloud_fetch_and_score():
    """Fetch RSS/Atom feeds. Scores with Claude API if ANTHROPIC_API_KEY is set."""
    settings = Settings()
    backend = get_backend(settings.db_path)

    try:
        # Reuse the standard ingestion pipeline (Twitter/XHS gracefully skip
        # when Chrome cookies are unavailable, i.e. in CI)
        total_new = await run_ingestion(backend, settings.config_dir)
        await _score_with_claude(backend, settings)

        logger.info(f"Cloud fetch complete: {total_new} new items")
        return total_new
    finally:
        backend.close()


async def cloud_fetch_all_users():
    """Fetch feeds for all users with configured sources in Supabase.

    Uses service role key to bypass RLS, then creates a scoped backend
    per user for data isolation.
    """
    settings = Settings()
    if not settings.supabase_url or not settings.supabase_service_key:
        logger.error("AINEWS_SUPABASE_URL and AINEWS_SUPABASE_SERVICE_KEY required")
        return 0

    try:
        from supabase import create_client
    except ImportError:
        logger.error("supabase package required. Install with: uv sync --extra supabase")
        return 0

    from ainews.sources.supabase_manager import (
        get_all_user_ids,
        get_user_sources,
        sources_to_config,
    )

    service_client = create_client(settings.supabase_url, settings.supabase_service_key)
    user_ids = get_all_user_ids(service_client)
    logger.info(f"Found {len(user_ids)} users with configured sources")

    total_new = 0
    for uid in user_ids:
        try:
            rows = get_user_sources(service_client, uid)
            if not rows:
                continue
            sources_config = sources_to_config(rows)
            backend = get_backend(user_id=uid)
            try:
                new_items = await run_ingestion(backend, sources_config=sources_config)
                total_new += new_items
                logger.info(f"User {uid}: fetched {new_items} new items")
                await _score_with_claude(backend, settings, label=f"User {uid}")
            finally:
                backend.close()
        except Exception:
            logger.exception(f"Failed to fetch for user {uid}")

    logger.info(
        f"Cloud fetch all users complete: {total_new} new items across {len(user_ids)} users"
    )
    return total_new
