"""Vercel Python serverless function — fetch a single source for an authenticated user.

POST /api/fetch-source
Headers: Authorization: Bearer <supabase-jwt>
Body: { "source_type": "rss", "name": "HN", "config": {"url": "..."}, "tags": ["tech"] }

Returns: { "items_fetched": N, "new_items": N }
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from ipaddress import ip_address
from urllib.parse import quote, urlparse

import feedparser
import httpx

from supabase import create_client

# Block SSRF: private/reserved IP ranges
_BLOCKED_RANGES = (
    "10.",
    "172.16.",
    "172.17.",
    "172.18.",
    "172.19.",
    "172.20.",
    "172.21.",
    "172.22.",
    "172.23.",
    "172.24.",
    "172.25.",
    "172.26.",
    "172.27.",
    "172.28.",
    "172.29.",
    "172.30.",
    "172.31.",
    "192.168.",
    "127.",
    "0.",
    "169.254.",
    "::1",
    "fd",
    "fe80",
)


def _is_safe_url(url: str) -> bool:
    """Block requests to private/internal IP ranges."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if host.lower() in ("localhost", "metadata.google.internal"):
        return False
    try:
        addr = ip_address(host)
        return addr.is_global
    except ValueError:
        # It's a hostname, not an IP — allow (DNS resolution may still resolve
        # to private, but httpx doesn't give us pre-connect hooks easily)
        return not any(host.startswith(r) for r in _BLOCKED_RANGES)


def _make_id(url: str, user_id: str | None = None) -> str:
    key = f"{user_id}:{url}" if user_id else url
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _parse_date(entry: dict) -> str | None:
    for field in ("published_parsed", "updated_parsed"):
        t = entry.get(field)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc).isoformat()
            except Exception:
                pass
    return None


def _build_feed_url(source_type: str, name: str, config: dict) -> dict | None:
    """Convert a user_sources row into a feed URL + metadata."""
    if source_type == "rss":
        return {"url": config["url"], "source_name": name, "source_type": "rss"}
    if source_type == "youtube":
        cid = config.get("channel_id", "")
        return {
            "url": f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}",
            "source_name": name,
            "source_type": "youtube",
        }
    if source_type == "arxiv":
        return {"url": config["url"], "source_name": name, "source_type": "arxiv"}
    if source_type == "arxiv_queries":
        query = config.get("query", "")
        return {
            "url": f"https://export.arxiv.org/api/query?search_query={quote(query)}"
            "&sortBy=submittedDate&sortOrder=descending&max_results=20",
            "source_name": name,
            "source_type": "arxiv",
        }
    if source_type == "rsshub":
        base = os.environ.get("AINEWS_RSSHUB_BASE", "https://rsshub.app")
        route = config.get("route", "")
        return {
            "url": f"{base}{route}",
            "source_name": name,
            "source_type": config.get("source_type", "rss"),
        }
    if source_type == "luma":
        base = os.environ.get("AINEWS_RSSHUB_BASE", "https://rsshub.app")
        handle = config.get("handle", name)
        return {
            "url": f"{base}/luma/{handle}",
            "source_name": f"Luma: {handle}",
            "source_type": "luma",
        }
    return None


def _fetch_and_ingest(supabase_client, user_id, source_type, name, config, tags):
    """Fetch one feed and write items to Supabase. Returns (fetched, new)."""
    feed_meta = _build_feed_url(source_type, name, config)
    if not feed_meta:
        return 0, 0

    url = feed_meta["url"]
    if not _is_safe_url(url):
        raise ValueError("Blocked URL: not allowed to fetch internal/private addresses")
    headers = {"User-Agent": "Mozilla/5.0 (compatible; ainews/0.1)"}
    resp = httpx.get(url, follow_redirects=True, timeout=15, headers=headers)
    resp.raise_for_status()

    feed = feedparser.parse(resp.text)
    items = []
    for entry in feed.entries:
        link = entry.get("link", "")
        if not link:
            continue
        summary = entry.get("summary", "")
        content = ""
        if entry.get("content"):
            content = entry["content"][0].get("value", "")
        items.append(
            {
                "p_id": _make_id(link, user_id),
                "p_url": link,
                "p_title": entry.get("title", "Untitled"),
                "p_summary": summary,
                "p_content": content,
                "p_source_name": feed_meta["source_name"],
                "p_source_type": feed_meta["source_type"],
                "p_tags": tags or [],
                "p_author": entry.get("author", ""),
                "p_published_at": _parse_date(entry),
                "p_fetched_at": datetime.now(timezone.utc).isoformat(),
                "p_user_id": user_id,
            }
        )

    if not items:
        return 0, 0

    # Check existing IDs
    item_ids = [i["p_id"] for i in items]
    existing = set()
    for i in range(0, len(item_ids), 500):
        chunk = item_ids[i : i + 500]
        resp = (
            supabase_client.table("items")
            .select("id")
            .in_("id", chunk)
            .eq("user_id", user_id)
            .execute()
        )
        existing.update(row["id"] for row in resp.data)

    new_count = 0
    for item in items:
        if item["p_id"] not in existing:
            supabase_client.rpc("upsert_item", item).execute()
            new_count += 1

    return len(items), new_count


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            # Read body
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}

            # Get JWT from Authorization header
            auth = self.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                self._json_response(401, {"error": "Missing Authorization header"})
                return
            jwt = auth[7:]

            supabase_url = os.environ.get("AINEWS_SUPABASE_URL", "")
            supabase_key = os.environ.get("AINEWS_SUPABASE_KEY", "")
            if not supabase_url or not supabase_key:
                self._json_response(500, {"error": "Supabase not configured"})
                return

            # Verify user identity from JWT
            client = create_client(supabase_url, supabase_key)
            user_resp = client.auth.get_user(jwt)
            if not user_resp or not user_resp.user:
                self._json_response(401, {"error": "Invalid token"})
                return
            user_id = user_resp.user.id

            # Use service key for writes (bypasses RLS, but we scope by user_id)
            service_key = os.environ.get("AINEWS_SUPABASE_SERVICE_KEY", "")
            if not service_key:
                self._json_response(500, {"error": "Server misconfigured"})
                return
            service_client = create_client(supabase_url, service_key)

            source_type = body.get("source_type", "")
            name = body.get("name", "")
            config = body.get("config", {})
            tags = body.get("tags", [])

            # Input validation
            if not source_type or not _build_feed_url(source_type, name or "_", config):
                self._json_response(400, {"error": f"Unsupported source_type: {source_type}"})
                return
            if not name or len(name) > 200:
                self._json_response(400, {"error": "name is required (max 200 chars)"})
                return
            if not isinstance(config, dict):
                self._json_response(400, {"error": "config must be an object"})
                return
            if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
                self._json_response(400, {"error": "tags must be a list of strings"})
                return

            fetched, new = _fetch_and_ingest(
                service_client, user_id, source_type, name, config, tags
            )

            self._json_response(
                200,
                {
                    "items_fetched": fetched,
                    "new_items": new,
                },
            )

        except Exception:
            self._json_response(500, {"error": "Internal server error"})

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def _json_response(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _cors_headers(self):
        allowed_origin = os.environ.get("AINEWS_CORS_ORIGIN", "")
        origin = self.headers.get("Origin", "")
        if allowed_origin and origin == allowed_origin:
            self.send_header("Access-Control-Allow-Origin", allowed_origin)
        # When AINEWS_CORS_ORIGIN is not set, don't send the header (deny cross-origin)
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
