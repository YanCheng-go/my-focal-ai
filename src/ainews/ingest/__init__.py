"""Ingestion utilities shared across all source fetchers."""

from datetime import datetime, timezone

SCRAPER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ainews/0.1; +https://github.com)",
}

# Max items to keep per trending page/category
MAX_TRENDING_ITEMS = 20


def utc_today() -> datetime:
    """Return today's date at midnight UTC."""
    return datetime.now(timezone.utc).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )


def rank_to_score(rank: int, total: int) -> float:
    """Convert a 1-based rank to a 0–1 score (higher = better)."""
    return round(1.0 - (rank - 1) / max(total, 1), 4)
