"""GitHub trending ingestion — fetches trending repos from trendshift.io."""

import json
import logging
import re
from datetime import datetime

import httpx

from ainews.models import ContentItem, make_id

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ainews/0.1; +https://github.com)"}
TRENDSHIFT_URL = "https://trendshift.io"


def _extract_repos_from_html(html: str) -> list[dict]:
    """Extract repo data from Next.js initialData JSON embedded in the page.

    The data is inside __next_f script tags as double-escaped JSON strings,
    so we first unescape the backslashes then parse the JSON array.
    """
    # Find the initialData array — it appears with escaped quotes: \"initialData\":[...]
    match = re.search(r'\\"initialData\\":\[', html)
    if not match:
        return []

    # Unescape the relevant chunk to get valid JSON
    start = match.start() + len('\\"initialData\\":')
    # Find the end of the array by tracking bracket depth on the unescaped text
    text = html[start:]
    # First unescape \" to "
    text = text.replace('\\"', '"')
    depth = 0
    end = 0
    for i, ch in enumerate(text):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end == 0:
        return []

    try:
        data = json.loads(text[:end])
    except json.JSONDecodeError:
        return []

    repos = []
    for obj in data:
        if "full_name" not in obj:
            continue
        repos.append(
            {
                "full_name": obj["full_name"],
                "description": obj.get("repository_description", ""),
                "stars": obj.get("repository_stars", 0),
                "language": obj.get("repository_language", ""),
                "rank": obj.get("rank", 0),
                "score": obj.get("score", 0),
            }
        )

    return repos


async def fetch_github_trending(tags: list[str] | None = None) -> list[ContentItem]:
    """Fetch trending repos from trendshift.io."""
    async with httpx.AsyncClient(timeout=30, headers=HEADERS) as client:
        resp = await client.get(TRENDSHIFT_URL, follow_redirects=True)
        resp.raise_for_status()

    repos = _extract_repos_from_html(resp.text)
    if not repos:
        logger.warning("No repos extracted from trendshift.io")
        return []

    # Deduplicate by full_name (regex may match same repo multiple times)
    seen = set()
    unique_repos = []
    for repo in repos:
        if repo["full_name"] not in seen:
            seen.add(repo["full_name"])
            unique_repos.append(repo)

    items = []
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    for repo in unique_repos:
        url = f"https://github.com/{repo['full_name']}"
        lang = repo["language"]
        stars = repo["stars"]
        rank = repo["rank"]

        summary_parts = []
        if repo["description"]:
            summary_parts.append(repo["description"])
        if lang:
            summary_parts.append(f"Language: {lang}")
        summary_parts.append(f"Stars: {stars:,}")
        summary_parts.append(f"Trending rank: #{rank}")

        items.append(
            ContentItem(
                id=make_id(f"{url}:{today.date()}"),
                url=url,
                title=f"#{rank} {repo['full_name']}",
                summary=" | ".join(summary_parts),
                source_name="GitHub Trending",
                source_type="github_trending",
                tags=tags or ["github", "trending", "open-source"],
                published_at=today,
            )
        )

    logger.info(f"Fetched {len(items)} trending repos from trendshift.io")
    return items


async def run_github_trending_ingestion(conn, sources_config: dict) -> int:
    """Fetch GitHub trending repos and store new items."""
    from ainews.storage.db import ingest_items

    sources = sources_config.get("sources", {})
    trending_config = sources.get("github_trending", {})
    if not trending_config:
        return 0

    tags = trending_config.get("tags", ["github", "trending", "open-source"])

    try:
        items = await fetch_github_trending(tags=tags)
        new_count = ingest_items(conn, "GitHub Trending", items)
        if new_count > 0:
            logger.info(f"Fetched {new_count} new trending repos")
        return new_count
    except Exception:
        logger.exception("Failed to fetch GitHub trending repos")
        return 0
