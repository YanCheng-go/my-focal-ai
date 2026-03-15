"""Shared constants and pure resolvers for URL → source field extraction.

Used by both src/ainews/sources/url_resolver.py (async, FastAPI) and
api/resolve_url.py (sync, Vercel serverless).
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# ── Host sets ──────────────────────────────────────────────────────

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
TWITTER_HOSTS = {"x.com", "twitter.com", "www.x.com", "www.twitter.com"}
ARXIV_HOSTS = {"arxiv.org", "www.arxiv.org"}
XHS_HOSTS = {"xiaohongshu.com", "www.xiaohongshu.com", "xhslink.com"}
LUMA_HOSTS = {"lu.ma", "www.lu.ma"}
RSSHUB_HOSTS = {"rsshub.app", "www.rsshub.app"}

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
                "url": (
                    f"https://export.arxiv.org/api/query?search_query=cat:{cat}"
                    "&sortBy=submittedDate&sortOrder=descending"
                    "&max_results=50"
                ),
                "name": f"arXiv:{cat}",
            },
            "suggested_tags": ["research"],
        }

    raise ValueError(f"Could not parse arXiv URL: {parsed.geturl()}")


def resolve_xiaohongshu(parsed: urlparse) -> dict:
    """Extract user_id from Xiaohongshu profile URLs."""
    path = parsed.path.strip("/")
    m = re.match(r"user/profile/([a-fA-F0-9]+)", path)
    if m:
        user_id = m.group(1)
        return {
            "source_type": "xiaohongshu",
            "fields": {"user_id": user_id, "name": f"XHS:{user_id[:8]}"},
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
