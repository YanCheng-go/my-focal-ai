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


def _ident(item: dict, key: str) -> str:
    """Normalise a repo identifier (``full_name`` or URL) for set comparison."""
    return str(item.get(key) or "").strip().lower()


def trending_new_entries(
    current: list[dict],
    previous: list[dict],
    key: str = "url",
) -> set[str]:
    """Return the identifiers of repos that entered the trending top list.

    Trending feeds are snapshot replacements (delete + re-insert), so a
    time-based "new since ``last_seen``" check flags every item on every fetch.
    Instead, compare the current snapshot against the previous snapshot by
    ``full_name``/URL and surface only the repos that are not in the previous
    set — the true "NEW" entries for the trends page badge.
    """
    previous_ids = {_ident(item, key) for item in previous} - {""}
    return {
        _ident(item, key)
        for item in current
        if _ident(item, key) not in previous_ids
    }
