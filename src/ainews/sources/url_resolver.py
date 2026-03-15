"""Resolve a pasted URL into source fields (channel_id, name, handle, etc.)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
_TWITTER_HOSTS = {"x.com", "twitter.com", "www.x.com", "www.twitter.com"}
_ARXIV_HOSTS = {"arxiv.org", "www.arxiv.org"}
_XHS_HOSTS = {"xiaohongshu.com", "www.xiaohongshu.com", "xhslink.com"}
_LUMA_HOSTS = {"lu.ma", "www.lu.ma"}
_RSSHUB_HOSTS = {"rsshub.app", "www.rsshub.app"}

# Patterns to extract channel_id from YouTube page source
_CHANNEL_ID_PATTERNS = [
    re.compile(r'"externalId"\s*:\s*"(UC[\w-]{22})"'),
    re.compile(r"/channel/(UC[\w-]{22})"),
    re.compile(r'"channelId"\s*:\s*"(UC[\w-]{22})"'),
]

_BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


@dataclass
class ResolvedSource:
    source_type: str
    fields: dict[str, str]
    suggested_tags: list[str] = field(default_factory=list)


async def resolve_url(url: str) -> ResolvedSource:
    """Accept any URL and return extracted source fields.

    Raises ValueError if the URL is not recognized or resolution fails.
    """
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urlparse(url)
    host = parsed.hostname or ""

    if host in _YOUTUBE_HOSTS:
        return await _resolve_youtube(url, parsed)
    if host in _TWITTER_HOSTS:
        return _resolve_twitter(parsed)
    if host in _ARXIV_HOSTS:
        return _resolve_arxiv(parsed)
    if host in _XHS_HOSTS:
        return _resolve_xiaohongshu(parsed)
    if host in _LUMA_HOSTS:
        return _resolve_luma(parsed)
    if host in _RSSHUB_HOSTS:
        return _resolve_rsshub(parsed)

    # Fallback: try RSS auto-discovery on any URL
    return await _resolve_generic(url)


# ── YouTube ──────────────────────────────────────────────────────────


async def _resolve_youtube(url: str, parsed: urlparse) -> ResolvedSource:
    """Resolve any YouTube URL to channel_id + name."""
    path = parsed.path.rstrip("/")

    # Direct /channel/UCxxx URL
    match = re.match(r"/channel/(UC[\w-]{22})", path)
    if match:
        channel_id = match.group(1)
        name = await _fetch_youtube_channel_name(channel_id)
        return ResolvedSource(
            source_type="youtube",
            fields={"channel_id": channel_id, "name": name},
        )

    # @handle URL — fetch page to get channel_id
    if path.startswith("/@"):
        channel_id, name = await _fetch_youtube_page_info(url)
        return ResolvedSource(
            source_type="youtube",
            fields={"channel_id": channel_id, "name": name},
        )

    # Video URL — use oEmbed to get channel info, then resolve channel_id
    if path.startswith(("/watch", "/shorts", "/live")) or parsed.hostname == "youtu.be":
        return await _resolve_youtube_video(url)

    raise ValueError(f"Could not parse YouTube URL: {url}")


async def _resolve_youtube_video(url: str) -> ResolvedSource:
    """Resolve a YouTube video/shorts/live URL via oEmbed + page scrape."""
    oembed_url = f"https://www.youtube.com/oembed?url={url}&format=json"
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(oembed_url)
        if resp.status_code != 200:
            raise ValueError(f"YouTube oEmbed failed (status {resp.status_code})")

        data = resp.json()
        author_name = data.get("author_name", "")
        author_url = data.get("author_url", "")

        # Fetch the channel page to get channel_id
        if author_url:
            channel_id, _ = await _fetch_youtube_page_info(author_url, client=client)
        else:
            raise ValueError("Could not determine channel from video")

    return ResolvedSource(
        source_type="youtube",
        fields={"channel_id": channel_id, "name": author_name},
    )


async def _fetch_youtube_page_info(
    page_url: str, *, client: httpx.AsyncClient | None = None
) -> tuple[str, str]:
    """Fetch a YouTube page and extract channel_id and name."""
    headers = {"User-Agent": _BROWSER_UA, "Cookie": "CONSENT=YES+1"}

    async def _fetch(c: httpx.AsyncClient) -> tuple[str, str]:
        resp = await c.get(page_url, headers=headers)
        resp.raise_for_status()
        text = resp.text

        channel_id = None
        for pat in _CHANNEL_ID_PATTERNS:
            m = pat.search(text)
            if m:
                channel_id = m.group(1)
                break
        if not channel_id:
            raise ValueError(f"Could not find channel_id on page: {page_url}")

        name_match = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', text)
        name = name_match.group(1) if name_match else ""

        return channel_id, name

    if client:
        return await _fetch(client)

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
        return await _fetch(c)


async def _fetch_youtube_channel_name(channel_id: str) -> str:
    """Fetch channel name for a known channel_id."""
    url = f"https://www.youtube.com/channel/{channel_id}"
    try:
        _, name = await _fetch_youtube_page_info(url)
        return name or channel_id
    except Exception:
        return channel_id


# ── Twitter/X ────────────────────────────────────────────────────────


def _resolve_twitter(parsed: urlparse) -> ResolvedSource:
    """Extract handle from a Twitter/X URL. No network call needed."""
    path = parsed.path.strip("/")
    handle = path.split("/")[0] if path else ""
    handle = handle.lstrip("@")

    if not handle or handle.lower() in {
        "home",
        "explore",
        "search",
        "settings",
        "i",
    }:
        raise ValueError(f"Could not extract handle from URL: {parsed.geturl()}")

    return ResolvedSource(
        source_type="twitter",
        fields={"handle": handle},
    )


# ── arXiv ────────────────────────────────────────────────────────────


def _resolve_arxiv(parsed: urlparse) -> ResolvedSource:
    """Resolve arxiv.org URLs to RSS feed URLs.

    Supports:
      - arxiv.org/abs/2405.12345 -> paper-specific (uses category feed)
      - arxiv.org/list/cs.AI/recent -> category listing
    """
    path = parsed.path.strip("/")

    # Paper URL: /abs/XXXX.XXXXX or /pdf/XXXX.XXXXX
    m = re.match(r"(?:abs|pdf)/(\d{4}\.\d{4,5})", path)
    if m:
        paper_id = m.group(1)
        # Use the paper ID as RSS query — user can refine
        return ResolvedSource(
            source_type="arxiv",
            fields={
                "url": f"https://export.arxiv.org/api/query?search_query=id:{paper_id}&max_results=50",
                "name": f"arXiv:{paper_id}",
            },
            suggested_tags=["research"],
        )

    # Category listing: /list/cs.AI/recent
    m = re.match(r"list/([\w.]+)", path)
    if m:
        category = m.group(1)
        return ResolvedSource(
            source_type="arxiv",
            fields={
                "url": f"https://export.arxiv.org/api/query?search_query=cat:{category}&sortBy=submittedDate&sortOrder=descending&max_results=50",
                "name": f"arXiv:{category}",
            },
            suggested_tags=["research"],
        )

    raise ValueError(f"Could not parse arXiv URL: {parsed.geturl()}")


# ── Xiaohongshu ──────────────────────────────────────────────────────


def _resolve_xiaohongshu(parsed: urlparse) -> ResolvedSource:
    """Extract user_id from Xiaohongshu profile URLs.

    Supports: xiaohongshu.com/user/profile/XXXXX
    """
    path = parsed.path.strip("/")

    m = re.match(r"user/profile/([a-fA-F0-9]+)", path)
    if m:
        user_id = m.group(1)
        return ResolvedSource(
            source_type="xiaohongshu",
            fields={"user_id": user_id, "name": f"XHS:{user_id[:8]}"},
        )

    raise ValueError(f"Could not parse Xiaohongshu URL: {parsed.geturl()}")


# ── Luma ─────────────────────────────────────────────────────────────


def _resolve_luma(parsed: urlparse) -> ResolvedSource:
    """Extract handle from lu.ma URLs.

    Supports: lu.ma/handle or lu.ma/event/xxx
    """
    path = parsed.path.strip("/")
    handle = path.split("/")[0] if path else ""

    if not handle:
        raise ValueError(f"Could not extract handle from Luma URL: {parsed.geturl()}")

    return ResolvedSource(
        source_type="luma",
        fields={"handle": handle},
    )


# ── RSSHub ───────────────────────────────────────────────────────────


def _resolve_rsshub(parsed: urlparse) -> ResolvedSource:
    """Extract route from rsshub.app URLs.

    Supports: rsshub.app/twitter/user/karpathy -> route: twitter/user/karpathy
    """
    route = parsed.path.strip("/")
    if not route:
        raise ValueError("Empty RSSHub route")

    # Use the last path segment as a reasonable name
    name = route.split("/")[-1]

    return ResolvedSource(
        source_type="rsshub",
        fields={"route": route, "name": f"RSSHub:{name}"},
    )


# ── Generic (RSS auto-discovery + fallback) ──────────────────────────


async def _resolve_generic(url: str) -> ResolvedSource:
    """Try RSS auto-discovery on any URL; fall back to leaderboard type."""
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        try:
            resp = await client.get(url, headers={"User-Agent": _BROWSER_UA})
            resp.raise_for_status()
        except Exception as exc:
            raise ValueError(f"Could not fetch URL: {exc}") from exc

        text = resp.text

        # Look for RSS/Atom feed links
        feed_match = re.search(
            r'<link[^>]+type="application/(?:rss|atom)\+xml"[^>]*>',
            text,
            re.IGNORECASE,
        )
        if feed_match:
            href_match = re.search(r'href="([^"]+)"', feed_match.group(0))
            if href_match:
                feed_url = href_match.group(1)
                # Make relative URLs absolute
                if feed_url.startswith("/"):
                    parsed = urlparse(url)
                    feed_url = f"{parsed.scheme}://{parsed.netloc}{feed_url}"

                # Extract page title for the name
                name = _extract_title(text) or urlparse(url).hostname or url

                return ResolvedSource(
                    source_type="rss",
                    fields={"url": feed_url, "name": name},
                )

        # No RSS found — offer as a leaderboard/event_links entry
        name = _extract_title(text) or urlparse(url).hostname or url
        return ResolvedSource(
            source_type="rss",
            fields={"url": url, "name": name},
        )


def _extract_title(html: str) -> str:
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
