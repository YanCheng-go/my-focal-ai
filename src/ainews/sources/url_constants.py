"""Shared constants and pure resolvers for URL → source field extraction.

Used by both src/ainews/sources/url_resolver.py (async, FastAPI) and
api/resolve_url.py (sync, Vercel serverless).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from urllib.parse import urlparse

_log = logging.getLogger(__name__)

# ── Host sets ──────────────────────────────────────────────────────

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
TWITTER_HOSTS = {"x.com", "twitter.com", "www.x.com", "www.twitter.com"}
ARXIV_HOSTS = {"arxiv.org", "www.arxiv.org"}
XHS_HOSTS = {"xiaohongshu.com", "www.xiaohongshu.com", "xhslink.com"}
LUMA_HOSTS = {"lu.ma", "www.lu.ma"}
RSSHUB_HOSTS = {"rsshub.app", "www.rsshub.app"}

# ── URL maps (auto-generated JSON, do not edit by hand) ───────────
# Run scripts/sync_rsshub_routes.py and scripts/sync_olshansk_feeds.py to update.

_HERE = Path(__file__).parent


def _load_json_map(filename: str) -> dict:
    path = _HERE / filename
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        _log.warning("URL map %s not found — URL map resolution disabled", filename)
        return {}


RSSHUB_URL_MAP: dict[str, str] = _load_json_map("rsshub_url_map.json")
OLSHANSK_FEED_MAP: dict[str, dict[str, str]] = _load_json_map("olshansk_feed_map.json")

# ── Regex patterns ─────────────────────────────────────────────────

CHANNEL_ID_PATTERNS = [
    re.compile(r'"externalId"\s*:\s*"(UC[\w-]{22})"'),
    re.compile(r"/channel/(UC[\w-]{22})"),
    re.compile(r'"channelId"\s*:\s*"(UC[\w-]{22})"'),
]

BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

_TWITTER_BLOCKED = {"home", "explore", "search", "settings", "i"}


# ── Pure resolvers (no network) ────────────────────────────────────


def resolve_twitter(parsed: urlparse) -> dict:
    """Extract handle from a Twitter/X URL."""
    path = parsed.path.strip("/")
    handle = path.split("/")[0].lstrip("@") if path else ""
    if not handle or handle.lower() in _TWITTER_BLOCKED:
        raise ValueError(f"Could not extract handle from URL: {parsed.geturl()}")
    return {"source_type": "twitter", "fields": {"handle": handle}, "suggested_tags": []}


def resolve_arxiv(parsed: urlparse) -> dict:
    """Resolve arxiv.org URLs to RSS feed URLs."""
    path = parsed.path.strip("/")

    m = re.match(r"(?:abs|pdf)/(\d{4}\.\d{4,5})", path)
    if m:
        paper_id = m.group(1)
        return {
            "source_type": "arxiv",
            "fields": {
                "url": f"https://export.arxiv.org/api/query?search_query=id:{paper_id}&max_results=50",
                "name": f"arXiv:{paper_id}",
            },
            "suggested_tags": ["research"],
        }

    m = re.match(r"list/([\w.]+)", path)
    if m:
        cat = m.group(1)
        return {
            "source_type": "arxiv",
            "fields": {
                "url": f"https://rss.arxiv.org/rss/{cat}",
                "name": f"arXiv:{cat}",
            },
            "suggested_tags": ["research"],
        }

    raise ValueError(f"Could not parse arXiv URL: {parsed.geturl()}")


def resolve_xiaohongshu(parsed: urlparse) -> dict:
    """Resolve Xiaohongshu profile URLs to an RSSHub route."""
    path = parsed.path.strip("/")
    m = re.match(r"user/profile/([a-fA-F0-9]+)", path)
    if m:
        user_id = m.group(1)
        return {
            "source_type": "rsshub",
            "fields": {
                "route": f"/xiaohongshu/user/{user_id}/notes",
                "name": f"XHS:{user_id[:8]}",
                "source_type": "xiaohongshu",
            },
            "suggested_tags": [],
        }
    raise ValueError(f"Could not parse Xiaohongshu URL: {parsed.geturl()}")


def resolve_luma(parsed: urlparse) -> dict:
    """Extract handle from lu.ma URLs."""
    path = parsed.path.strip("/")
    handle = path.split("/")[0] if path else ""
    if not handle:
        raise ValueError(f"Could not extract handle from Luma URL: {parsed.geturl()}")
    return {"source_type": "luma", "fields": {"handle": handle}, "suggested_tags": []}


def resolve_rsshub(parsed: urlparse) -> dict:
    """Extract route from rsshub.app URLs."""
    route = parsed.path.strip("/")
    if not route:
        raise ValueError("Empty RSSHub route")
    name = route.split("/")[-1]
    return {
        "source_type": "rsshub",
        "fields": {"route": route, "name": f"RSSHub:{name}"},
        "suggested_tags": [],
    }


def _url_lookup_keys(parsed: urlparse) -> list[str]:
    """Return candidate lookup keys for a parsed URL, from most to least specific.

    Tries exact host+path, www-stripped host+path, and host-only fallback.
    Deduplicates while preserving order.
    """
    hostname = parsed.hostname or ""
    bare = hostname.removeprefix("www.")
    path = parsed.path.rstrip("/")
    candidates = [f"{hostname}{path}", f"{bare}{path}", hostname, bare]
    if bare != hostname:
        # Also try the www. variant when input didn't have it
        candidates.insert(1, f"www.{bare}{path}")
    seen: set[str] = set()
    keys = []
    for key in candidates:
        if key and key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def resolve_rsshub_for_url(parsed: urlparse) -> dict | None:
    """Return an RSSHub source if the pasted website URL has a known RSSHub route."""
    for key in _url_lookup_keys(parsed):
        route = RSSHUB_URL_MAP.get(key)
        if route:
            name = route.split("/")[-1]
            return {
                "source_type": "rsshub",
                "fields": {"route": route, "name": f"RSSHub:{name}"},
                "suggested_tags": [],
            }
    return None


def resolve_olshansk(parsed: urlparse) -> dict | None:
    """Return an RSS source using the Olshansk feed mirror if the URL is known."""
    for key in _url_lookup_keys(parsed):
        entry = OLSHANSK_FEED_MAP.get(key)
        if entry:
            name = entry["name"] if isinstance(entry, dict) else key.split("/")[-1].title()
            url = entry["url"] if isinstance(entry, dict) else entry
            return {
                "source_type": "rss",
                "fields": {"url": url, "name": name},
                "suggested_tags": [],
            }
    return None


def extract_title(html: str) -> str:
    """Extract <title> or og:title from HTML."""
    m = re.search(
        r'<meta\s+property="og:title"\s+content="([^"]+)"',
        html,
        re.IGNORECASE,
    )
    if m:
        return m.group(1)
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""
