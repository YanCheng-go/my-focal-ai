"""Feed ingestion — fetches RSS/Atom feeds and normalizes to ContentItem."""

from datetime import datetime, timezone

import feedparser
import httpx

from ainews.models import ContentItem, make_id


def _parse_date(entry: dict) -> datetime | None:
    for field in ("published_parsed", "updated_parsed"):
        t = entry.get(field)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
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
    headers = {"User-Agent": "Mozilla/5.0 (compatible; ainews/0.1; +https://github.com)"}
    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
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

        items.append(
            ContentItem(
                id=make_id(url),
                url=url,
                title=entry.get("title", "Untitled"),
                summary=summary,
                content=content,
                source_name=source_name,
                source_type=source_type,
                tags=tags or [],
                author=entry.get("author", ""),
                published_at=_parse_date(entry),
            )
        )

    return items


def build_feed_urls(sources_config: dict) -> list[dict]:
    """Convert sources.yml config into a list of feed URLs with metadata."""
    rsshub_base = sources_config.get("rsshub_base", "http://localhost:1200")
    sources = sources_config.get("sources", {})
    feeds = []

    # Twitter is handled separately (see ingest/twitter.py)
    # Xiaohongshu is handled separately (see ingest/xiaohongshu.py)

    # YouTube native RSS
    for ch in sources.get("youtube", []):
        cid = ch["channel_id"]
        feeds.append(
            {
                "url": f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}",
                "source_name": ch.get("name", cid),
                "source_type": "youtube",
                "tags": ch.get("tags", []),
            }
        )

    # ArXiv category RSS feeds
    for feed in sources.get("arxiv", []):
        feeds.append(
            {
                "url": feed["url"],
                "source_name": feed.get("name", feed["url"]),
                "source_type": "arxiv",
                "tags": feed.get("tags", []),
            }
        )

    # Direct RSS feeds
    for feed in sources.get("rss", []):
        feeds.append(
            {
                "url": feed["url"],
                "source_name": feed.get("name", feed["url"]),
                "source_type": "rss",
                "tags": feed.get("tags", []),
            }
        )

    # Generic RSSHub routes (for sites without native RSS)
    for item in sources.get("rsshub", []):
        feeds.append(
            {
                "url": f"{rsshub_base}{item['route']}",
                "source_name": item.get("name", item["route"]),
                "source_type": item.get("source_type", "rss"),
                "tags": item.get("tags", []),
            }
        )

    # Luma events via RSSHub
    for event in sources.get("luma", []):
        handle = event["handle"]
        feeds.append(
            {
                "url": f"{rsshub_base}/luma/{handle}",
                "source_name": f"Luma: {handle}",
                "source_type": "luma",
                "tags": event.get("tags", []),
            }
        )

    # ArXiv keyword queries (Atom API)
    for aq in sources.get("arxiv_queries", []):
        query = aq["query"]
        feeds.append(
            {
                "url": f"https://export.arxiv.org/api/query?search_query={query}&sortBy=submittedDate&sortOrder=descending&max_results=20",
                "source_name": aq.get("name", f"arXiv: {query}"),
                "source_type": "arxiv",
                "tags": aq.get("tags", []),
            }
        )

    return feeds
