"""Vercel Python serverless function — resolve a URL into source fields.

POST /api/resolve-url
Headers: Authorization: Bearer <supabase-jwt>
Body: { "url": "https://youtube.com/watch?v=..." }

Returns: { "source_type": "youtube", "fields": {...}, "suggested_tags": [] }
"""

import json
import os
import re
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

import httpx

_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
}
_TWITTER_HOSTS = {
    "x.com",
    "twitter.com",
    "www.x.com",
    "www.twitter.com",
}
_ARXIV_HOSTS = {"arxiv.org", "www.arxiv.org"}
_XHS_HOSTS = {
    "xiaohongshu.com",
    "www.xiaohongshu.com",
    "xhslink.com",
}
_LUMA_HOSTS = {"lu.ma", "www.lu.ma"}
_RSSHUB_HOSTS = {"rsshub.app", "www.rsshub.app"}

_CHANNEL_ID_PATTERNS = [
    re.compile(r'"externalId"\s*:\s*"(UC[\w-]{22})"'),
    re.compile(r"/channel/(UC[\w-]{22})"),
    re.compile(r'"channelId"\s*:\s*"(UC[\w-]{22})"'),
]
_BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def _cors_headers() -> dict:
    origin = os.environ.get("AINEWS_CORS_ORIGIN", "*")
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
    }


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


# ── Twitter ──────────────────────────────────────────────────────


def _resolve_twitter(parsed) -> dict:
    path = parsed.path.strip("/")
    handle = path.split("/")[0].lstrip("@") if path else ""
    blocked = {"home", "explore", "search", "settings", "i"}
    if not handle or handle.lower() in blocked:
        raise ValueError("Could not extract handle from URL")
    return _result("twitter", {"handle": handle})


# ── YouTube ──────────────────────────────────────────────────────


def _resolve_youtube(url: str, parsed) -> dict:
    path = parsed.path.rstrip("/")

    m = re.match(r"/channel/(UC[\w-]{22})", path)
    if m:
        channel_id = m.group(1)
        name = _fetch_yt_name(channel_id)
        return _result(
            "youtube",
            {
                "channel_id": channel_id,
                "name": name,
            },
        )

    if path.startswith("/@"):
        channel_id, name = _fetch_yt_page_info(url)
        return _result(
            "youtube",
            {
                "channel_id": channel_id,
                "name": name,
            },
        )

    is_video = path.startswith(("/watch", "/shorts", "/live")) or parsed.hostname == "youtu.be"
    if is_video:
        oembed = f"https://www.youtube.com/oembed?url={url}&format=json"
        resp = httpx.get(
            oembed,
            timeout=10,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            raise ValueError(f"YouTube oEmbed failed (status {resp.status_code})")
        data = resp.json()
        author_name = data.get("author_name", "")
        author_url = data.get("author_url", "")
        if not author_url:
            raise ValueError("Could not determine channel from video")
        channel_id, _ = _fetch_yt_page_info(author_url)
        return _result(
            "youtube",
            {
                "channel_id": channel_id,
                "name": author_name,
            },
        )

    raise ValueError(f"Could not parse YouTube URL: {url}")


def _fetch_yt_page_info(page_url: str) -> tuple:
    headers = {
        "User-Agent": _BROWSER_UA,
        "Cookie": "CONSENT=YES+1",
    }
    resp = httpx.get(
        page_url,
        headers=headers,
        timeout=15,
        follow_redirects=True,
    )
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
    name_match = re.search(
        r'<meta\s+property="og:title"\s+content="([^"]+)"',
        text,
    )
    name = name_match.group(1) if name_match else ""
    return channel_id, name


def _fetch_yt_name(channel_id: str) -> str:
    try:
        url = f"https://www.youtube.com/channel/{channel_id}"
        _, name = _fetch_yt_page_info(url)
        return name or channel_id
    except Exception:
        return channel_id


# ── arXiv ────────────────────────────────────────────────────────


def _resolve_arxiv(parsed) -> dict:
    path = parsed.path.strip("/")

    m = re.match(r"(?:abs|pdf)/(\d{4}\.\d{4,5})", path)
    if m:
        paper_id = m.group(1)
        base = "https://export.arxiv.org/api/query"
        url = f"{base}?search_query=id:{paper_id}&max_results=50"
        return _result(
            "arxiv",
            {"url": url, "name": f"arXiv:{paper_id}"},
            ["research"],
        )

    m = re.match(r"list/([\w.]+)", path)
    if m:
        cat = m.group(1)
        base = "https://export.arxiv.org/api/query"
        url = (
            f"{base}?search_query=cat:{cat}"
            "&sortBy=submittedDate&sortOrder=descending"
            "&max_results=50"
        )
        return _result(
            "arxiv",
            {"url": url, "name": f"arXiv:{cat}"},
            ["research"],
        )

    raise ValueError(f"Could not parse arXiv URL: {parsed.geturl()}")


# ── Xiaohongshu ──────────────────────────────────────────────────


def _resolve_xiaohongshu(parsed) -> dict:
    path = parsed.path.strip("/")
    m = re.match(r"user/profile/([a-fA-F0-9]+)", path)
    if m:
        user_id = m.group(1)
        return _result(
            "xiaohongshu",
            {
                "user_id": user_id,
                "name": f"XHS:{user_id[:8]}",
            },
        )
    raise ValueError(f"Could not parse Xiaohongshu URL: {parsed.geturl()}")


# ── Luma ─────────────────────────────────────────────────────────


def _resolve_luma(parsed) -> dict:
    path = parsed.path.strip("/")
    handle = path.split("/")[0] if path else ""
    if not handle:
        raise ValueError("Could not extract Luma handle")
    return _result("luma", {"handle": handle})


# ── RSSHub ───────────────────────────────────────────────────────


def _resolve_rsshub(parsed) -> dict:
    route = parsed.path.strip("/")
    if not route:
        raise ValueError("Empty RSSHub route")
    name = route.split("/")[-1]
    return _result(
        "rsshub",
        {
            "route": route,
            "name": f"RSSHub:{name}",
        },
    )


# ── Generic (RSS auto-discovery) ─────────────────────────────────


def _extract_title(html: str) -> str:
    m = re.search(
        r'<meta\s+property="og:title"\s+content="([^"]+)"',
        html,
        re.IGNORECASE,
    )
    if m:
        return m.group(1)
    m = re.search(
        r"<title[^>]*>([^<]+)</title>",
        html,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    return ""


def _resolve_generic(url: str) -> dict:
    try:
        resp = httpx.get(
            url,
            headers={"User-Agent": _BROWSER_UA},
            timeout=10,
            follow_redirects=True,
        )
        resp.raise_for_status()
    except Exception as exc:
        raise ValueError(f"Could not fetch URL: {exc}") from exc

    text = resp.text
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

    name = _extract_title(text) or urlparse(url).hostname or url
    return _result(
        "rss",
        {
            "url": feed_url or url,
            "name": name,
        },
    )


# ── Dispatch ─────────────────────────────────────────────────────


def _resolve(url: str) -> dict:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    host = parsed.hostname or ""

    if host in _YOUTUBE_HOSTS:
        return _resolve_youtube(url, parsed)
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

    return _resolve_generic(url)


# ── Handler ──────────────────────────────────────────────────────


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        for k, v in _cors_headers().items():
            self.send_header(k, v)
        self.end_headers()

    def do_POST(self):
        cors = _cors_headers()

        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return self._json(
                401,
                {"error": "Missing Authorization header"},
                cors,
            )
        user = _verify_jwt(auth[7:])
        if not user:
            return self._json(
                401,
                {"error": "Invalid or expired token"},
                cors,
            )

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        url = body.get("url", "").strip()
        if not url:
            return self._json(
                400,
                {"error": "URL is required"},
                cors,
            )

        try:
            result = _resolve(url)
            return self._json(200, result, cors)
        except ValueError as e:
            return self._json(400, {"error": str(e)}, cors)
        except Exception as e:
            return self._json(500, {"error": str(e)}, cors)

    def _json(self, status, data, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
