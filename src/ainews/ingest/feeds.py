"""Feed ingestion — fetches RSS/Atom feeds and normalizes to ContentItem."""

import hashlib
from datetime import datetime

import feedparser
import httpx

from ainews.models import ContentItem


def _make_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _parse_date(entry: dict) -> datetime | None:
    for field in ("published_parsed", "updated_parsed"):
        t = entry.get(field)
        if t:
            try:
                return datetime(*t[:6])
            except Exception:
                pass
    return None


async def fetch_feed(
    url: str,
    source_name: str,
    source_type: str,
    tags: list[str] | None = None,
) -> list[ContentItem]:
    """Fetch and parse a single RSS/Atom feed URL."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()

    feed = feedparser.parse(resp.text)
    items = []

    for entry in feed.entries:
        url = entry.get("link", "")
        if not url:
            continue

        summary = entry.get("summary", "")
        content = ""
        if entry.get("content"):
            content = entry["content"][0].get("value", "")

        items.append(ContentItem(
            id=_make_id(url),
            url=url,
            title=entry.get("title", "Untitled"),
            summary=summary,
            content=content,
            source_name=source_name,
            source_type=source_type,
            tags=tags or [],
            author=entry.get("author", ""),
            published_at=_parse_date(entry),
        ))

    return items


def build_feed_urls(sources_config: dict) -> list[dict]:
    """Convert sources.yml config into a list of feed URLs with metadata."""
    rsshub_base = sources_config.get("rsshub_base", "http://localhost:1200")
    sources = sources_config.get("sources", {})
    feeds = []

    # Twitter via RSSHub
    for user in sources.get("twitter", []):
        handle = user["handle"]
        feeds.append({
            "url": f"{rsshub_base}/twitter/user/{handle}",
            "source_name": f"@{handle}",
            "source_type": "twitter",
            "tags": user.get("tags", []),
        })

    # Xiaohongshu via RSSHub
    for user in sources.get("xiaohongshu", []):
        uid = user["user_id"]
        feeds.append({
            "url": f"{rsshub_base}/xiaohongshu/user/{uid}/notes",
            "source_name": user.get("name", uid),
            "source_type": "xiaohongshu",
            "tags": user.get("tags", []),
        })

    # YouTube native RSS
    for ch in sources.get("youtube", []):
        cid = ch["channel_id"]
        feeds.append({
            "url": f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}",
            "source_name": ch.get("name", cid),
            "source_type": "youtube",
            "tags": ch.get("tags", []),
        })

    # Direct RSS feeds
    for feed in sources.get("rss", []):
        feeds.append({
            "url": feed["url"],
            "source_name": feed.get("name", feed["url"]),
            "source_type": "rss",
            "tags": feed.get("tags", []),
        })

    return feeds
