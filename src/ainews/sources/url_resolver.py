"""Resolve a pasted URL into source fields (channel_id, name, handle, etc.)."""

from __future__ import annotations

import re
import socket
from dataclasses import dataclass, field
from ipaddress import ip_address
from urllib.parse import quote, urlparse

import httpx

from ainews.sources.url_constants import (
    ARXIV_HOSTS,
    BROWSER_UA,
    CHANNEL_ID_PATTERNS,
    LUMA_HOSTS,
    RSSHUB_HOSTS,
    TWITTER_HOSTS,
    XHS_HOSTS,
    YOUTUBE_HOSTS,
    extract_title,
    resolve_arxiv,
    resolve_luma,
    resolve_olshansk,
    resolve_rsshub,
    resolve_rsshub_for_url,
    resolve_twitter,
    resolve_xiaohongshu,
)

# Hostnames always blocked (never attempt DNS resolution)
_BLOCKED_HOSTS = {"localhost", "metadata.google.internal"}


def _is_safe_url(url: str) -> bool:
    """Block requests to private/internal IP ranges."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if host.lower() in _BLOCKED_HOSTS:
        return False
    try:
        addr = ip_address(host)
        return addr.is_global
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False
    if not infos:
        return False
    for info in infos:
        addr = ip_address(info[4][0])
        if not addr.is_global:
            return False
    return True


@dataclass
class ResolvedSource:
    source_type: str
    fields: dict[str, str]
    suggested_tags: list[str] = field(default_factory=list)


def _to_resolved(d: dict) -> ResolvedSource:
    """Convert a plain dict from url_constants to a ResolvedSource."""
    return ResolvedSource(
        source_type=d["source_type"],
        fields=d["fields"],
        suggested_tags=d.get("suggested_tags", []),
    )


async def resolve_url(url: str) -> ResolvedSource:
    """Accept any URL and return extracted source fields.

    Raises ValueError if the URL is not recognized or resolution fails.
    """
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urlparse(url)
    host = parsed.hostname or ""

    if host in YOUTUBE_HOSTS:
        return await _resolve_youtube(url, parsed)
    if host in TWITTER_HOSTS:
        return _to_resolved(resolve_twitter(parsed))
    if host in ARXIV_HOSTS:
        return _to_resolved(resolve_arxiv(parsed))
    if host in XHS_HOSTS:
        return _to_resolved(resolve_xiaohongshu(parsed))
    if host in LUMA_HOSTS:
        return _to_resolved(resolve_luma(parsed))
    if host in RSSHUB_HOSTS:
        return _to_resolved(resolve_rsshub(parsed))
    # Prefer RSSHub route over Olshansk for known overlapping sites
    rsshub_for_url = resolve_rsshub_for_url(parsed)
    if rsshub_for_url:
        return _to_resolved(rsshub_for_url)

    # Check Olshansk feed mirror before generic auto-discovery
    olshansk = resolve_olshansk(parsed)
    if olshansk:
        return _to_resolved(olshansk)

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
    oembed_url = f"https://www.youtube.com/oembed?url={quote(url, safe='')}&format=json"
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(oembed_url)
        if resp.status_code != 200:
            raise ValueError(f"YouTube oEmbed failed (status {resp.status_code})")

        data = resp.json()
        author_name = data.get("author_name", "")
        author_url = data.get("author_url", "")

        # Validate author_url points to YouTube before following it
        if not author_url:
            raise ValueError("Could not determine channel from video")
        author_host = urlparse(author_url).hostname or ""
        if author_host not in YOUTUBE_HOSTS:
            raise ValueError("Unexpected author URL from oEmbed")
        channel_id, _ = await _fetch_youtube_page_info(author_url, client=client)

    return ResolvedSource(
        source_type="youtube",
        fields={"channel_id": channel_id, "name": author_name},
    )


async def _fetch_youtube_page_info(
    page_url: str, *, client: httpx.AsyncClient | None = None
) -> tuple[str, str]:
    """Fetch a YouTube page and extract channel_id and name."""
    if not _is_safe_url(page_url):
        raise ValueError("Blocked URL: not allowed to fetch internal/private addresses")
    headers = {"User-Agent": BROWSER_UA, "Cookie": "CONSENT=YES+1"}

    async def _fetch(c: httpx.AsyncClient) -> tuple[str, str]:
        resp = await c.get(page_url, headers=headers)
        if resp.status_code != 200:
            raise ValueError(f"YouTube page fetch failed (status {resp.status_code})")
        text = resp.text

        channel_id = None
        for pat in CHANNEL_ID_PATTERNS:
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


# ── Generic (RSS auto-discovery + fallback) ──────────────────────────


async def _resolve_generic(url: str) -> ResolvedSource:
    """Try RSS auto-discovery on any URL; fall back to leaderboard type."""
    if not _is_safe_url(url):
        raise ValueError("Blocked URL: not allowed to fetch internal/private addresses")
    # Only read first 64KB — RSS/title tags are always in <head>
    max_bytes = 65536
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        try:
            async with client.stream("GET", url, headers={"User-Agent": BROWSER_UA}) as resp:
                resp.raise_for_status()
                chunks: list[bytes] = []
                total = 0
                async for chunk in resp.aiter_bytes():
                    chunks.append(chunk)
                    total += len(chunk)
                    if total >= max_bytes:
                        break
                text = b"".join(chunks).decode("utf-8", errors="replace")
        except Exception as exc:
            raise ValueError("Could not fetch URL") from exc

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
                name = extract_title(text) or urlparse(url).hostname or url

                return ResolvedSource(
                    source_type="rss",
                    fields={"url": feed_url, "name": name},
                )

        # No RSS found — offer as a leaderboard/event_links entry
        name = extract_title(text) or urlparse(url).hostname or url
        return ResolvedSource(
            source_type="rss",
            fields={"url": url, "name": name},
        )
