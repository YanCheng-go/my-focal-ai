"""Vercel Python serverless function — resolve a URL into source fields.

POST /api/resolve-url
Headers: Authorization: Bearer <supabase-jwt>
Body: { "url": "https://youtube.com/watch?v=..." }

Returns: { "source_type": "youtube", "fields": {...}, "suggested_tags": [] }
"""

import json
import os
import re
import socket
from http.server import BaseHTTPRequestHandler
from ipaddress import ip_address
from urllib.parse import urlparse

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
    resolve_rsshub,
    resolve_twitter,
    resolve_xiaohongshu,
)

_MAX_BODY_SIZE = 4096

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


def _cors_headers(request_origin: str = "") -> dict:
    allowed = os.environ.get("AINEWS_CORS_ORIGIN", "")
    headers = {
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
    }
    if allowed and request_origin == allowed:
        headers["Access-Control-Allow-Origin"] = allowed
    return headers


def _verify_jwt(jwt: str) -> dict | None:
    """Verify JWT via Supabase Auth and return user dict."""
    base_url = os.environ.get("AINEWS_SUPABASE_URL", "")
    anon_key = os.environ.get("AINEWS_SUPABASE_KEY", "")
    if not base_url or not anon_key:
        return None
    resp = httpx.get(
        f"{base_url}/auth/v1/user",
        headers={
            "apikey": anon_key,
            "Authorization": f"Bearer {jwt}",
        },
        timeout=5,
    )
    if resp.status_code != 200:
        return None
    return resp.json()


def _result(source_type, fields, tags=None):
    return {
        "source_type": source_type,
        "fields": fields,
        "suggested_tags": tags or [],
    }


# ── YouTube (sync, needs network) ────────────────────────────────


def _resolve_youtube(url: str, parsed) -> dict:
    path = parsed.path.rstrip("/")

    m = re.match(r"/channel/(UC[\w-]{22})", path)
    if m:
        channel_id = m.group(1)
        name = _fetch_yt_name(channel_id)
        return _result("youtube", {"channel_id": channel_id, "name": name})

    if path.startswith("/@"):
        channel_id, name = _fetch_yt_page_info(url)
        return _result("youtube", {"channel_id": channel_id, "name": name})

    is_video = path.startswith(("/watch", "/shorts", "/live")) or parsed.hostname == "youtu.be"
    if is_video:
        oembed = f"https://www.youtube.com/oembed?url={url}&format=json"
        resp = httpx.get(oembed, timeout=10, follow_redirects=True)
        if resp.status_code != 200:
            raise ValueError(f"YouTube oEmbed failed (status {resp.status_code})")
        data = resp.json()
        author_name = data.get("author_name", "")
        author_url = data.get("author_url", "")
        if not author_url:
            raise ValueError("Could not determine channel from video")
        channel_id, _ = _fetch_yt_page_info(author_url)
        return _result("youtube", {"channel_id": channel_id, "name": author_name})

    raise ValueError(f"Could not parse YouTube URL: {url}")


def _fetch_yt_page_info(page_url: str) -> tuple:
    headers = {"User-Agent": BROWSER_UA, "Cookie": "CONSENT=YES+1"}
    resp = httpx.get(page_url, headers=headers, timeout=15, follow_redirects=True)
    resp.raise_for_status()
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


def _fetch_yt_name(channel_id: str) -> str:
    try:
        url = f"https://www.youtube.com/channel/{channel_id}"
        _, name = _fetch_yt_page_info(url)
        return name or channel_id
    except Exception:
        return channel_id


# ── Generic (RSS auto-discovery, sync, needs network) ────────────


def _resolve_generic(url: str) -> dict:
    if not _is_safe_url(url):
        raise ValueError("Blocked URL: not allowed to fetch internal/private addresses")
    # Only read first 64KB — RSS/title tags are always in <head>
    max_bytes = 65536
    try:
        with httpx.stream(
            "GET", url, headers={"User-Agent": BROWSER_UA}, timeout=10, follow_redirects=True
        ) as resp:
            resp.raise_for_status()
            chunks = []
            total = 0
            for chunk in resp.iter_bytes():
                chunks.append(chunk)
                total += len(chunk)
                if total >= max_bytes:
                    break
            text = b"".join(chunks).decode("utf-8", errors="replace")
    except Exception as exc:
        raise ValueError("Could not fetch URL") from exc
    feed_match = re.search(
        r'<link[^>]+type="application/(?:rss|atom)\+xml"[^>]*>',
        text,
        re.IGNORECASE,
    )
    feed_url = None
    if feed_match:
        href = re.search(r'href="([^"]+)"', feed_match.group(0))
        if href:
            feed_url = href.group(1)
            if feed_url.startswith("/"):
                p = urlparse(url)
                feed_url = f"{p.scheme}://{p.netloc}{feed_url}"

    name = extract_title(text) or urlparse(url).hostname or url
    return _result("rss", {"url": feed_url or url, "name": name})


# ── Dispatch ─────────────────────────────────────────────────────


def _resolve(url: str) -> dict:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    host = parsed.hostname or ""

    if host in YOUTUBE_HOSTS:
        return _resolve_youtube(url, parsed)
    if host in TWITTER_HOSTS:
        return resolve_twitter(parsed)
    if host in ARXIV_HOSTS:
        return resolve_arxiv(parsed)
    if host in XHS_HOSTS:
        return resolve_xiaohongshu(parsed)
    if host in LUMA_HOSTS:
        return resolve_luma(parsed)
    if host in RSSHUB_HOSTS:
        return resolve_rsshub(parsed)

    return _resolve_generic(url)


# ── Handler ──────────────────────────────────────────────────────


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        origin = self.headers.get("Origin", "")
        for k, v in _cors_headers(origin).items():
            self.send_header(k, v)
        self.end_headers()

    def do_POST(self):
        origin = self.headers.get("Origin", "")
        cors = _cors_headers(origin)

        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return self._json(401, {"error": "Missing Authorization header"}, cors)
        user = _verify_jwt(auth[7:])
        if not user:
            return self._json(401, {"error": "Invalid or expired token"}, cors)

        length = int(self.headers.get("Content-Length", 0))
        if length > _MAX_BODY_SIZE:
            return self._json(413, {"error": "Request body too large"}, cors)
        try:
            body = json.loads(self.rfile.read(length)) if length else {}
        except (json.JSONDecodeError, ValueError):
            return self._json(400, {"error": "Invalid JSON body"}, cors)
        url = body.get("url", "").strip()
        if not url:
            return self._json(400, {"error": "URL is required"}, cors)

        try:
            result = _resolve(url)
            return self._json(200, result, cors)
        except ValueError as e:
            return self._json(400, {"error": str(e)}, cors)
        except Exception:
            return self._json(500, {"error": "Internal server error"}, cors)

    def _json(self, status, data, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
