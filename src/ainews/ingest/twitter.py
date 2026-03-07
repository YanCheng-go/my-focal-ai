"""Twitter ingestion via twscrape — no API keys needed, just a Twitter account."""

import hashlib
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from twscrape import API, gather

from ainews.models import ContentItem
from ainews.storage.db import upsert_item

logger = logging.getLogger(__name__)

TWSCRAPE_DB = Path("data/twscrape.db")


def _make_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


async def setup_twitter_account(username: str, password: str, email: str):
    """Add and login a Twitter account for scraping. Run once."""
    TWSCRAPE_DB.parent.mkdir(parents=True, exist_ok=True)
    api = API(str(TWSCRAPE_DB))
    await api.pool.add_account(username, password, email, password)
    await api.pool.login_all()
    logger.info(f"Twitter account @{username} logged in for scraping")


async def fetch_twitter_user(
    handle: str,
    tags: list[str] | None = None,
    limit: int = 20,
) -> list[ContentItem]:
    """Fetch recent tweets from a user."""
    api = API(str(TWSCRAPE_DB))

    try:
        user = await api.user_by_login(handle)
        if not user:
            logger.warning(f"Twitter user @{handle} not found")
            return []

        tweets = await gather(api.user_tweets(user.id, limit=limit))
    except Exception:
        logger.exception(f"Failed to fetch tweets from @{handle}")
        return []

    items = []
    for tweet in tweets:
        url = f"https://x.com/{handle}/status/{tweet.id}"
        items.append(ContentItem(
            id=_make_id(url),
            url=url,
            title=tweet.rawContent[:100] + ("..." if len(tweet.rawContent) > 100 else ""),
            summary=tweet.rawContent,
            content=tweet.rawContent,
            source_name=f"@{handle}",
            source_type="twitter",
            tags=tags or [],
            author=handle,
            published_at=tweet.date,
        ))

    return items


async def run_twitter_ingestion(conn: sqlite3.Connection, sources_config: dict):
    """Fetch all configured Twitter sources."""
    sources = sources_config.get("sources", {})
    twitter_users = sources.get("twitter", [])

    if not twitter_users:
        return 0

    total = 0
    for user in twitter_users:
        handle = user["handle"]
        try:
            items = await fetch_twitter_user(handle, tags=user.get("tags", []))
            for item in items:
                upsert_item(conn, item)
            total += len(items)
            logger.info(f"Fetched {len(items)} tweets from @{handle}")
        except Exception:
            logger.exception(f"Failed to fetch @{handle}")

    return total
