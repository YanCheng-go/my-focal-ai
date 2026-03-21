"""Vercel Python serverless function — explore new sources via Claude API.

POST /api/explore
Headers: Authorization: Bearer <supabase-jwt>
Body: { "source_type": "twitter", "min_score": 0.5, "limit": 10 }

Returns: { "suggestions": [...] }
"""

import json
import os
import re
from http.server import BaseHTTPRequestHandler

import httpx

# ---------------------------------------------------------------------------
# Supabase helpers (same pattern as fetch_source.py)
# ---------------------------------------------------------------------------


def _sb_get_user(base_url: str, anon_key: str, jwt: str) -> dict | None:
    resp = httpx.get(
        f"{base_url}/auth/v1/user",
        headers={"apikey": anon_key, "Authorization": f"Bearer {jwt}"},
        timeout=5,
    )
    if resp.status_code != 200:
        return None
    return resp.json()


def _sb_get_sources(base_url: str, service_key: str, user_id: str) -> list[dict]:
    """Get user's sources from Supabase."""
    resp = httpx.get(
        f"{base_url}/rest/v1/user_sources",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
        },
        params={
            "select": "source_type,name,config,tags",
            "user_id": f"eq.{user_id}",
            "disabled": "eq.false",
        },
        timeout=5,
    )
    if resp.status_code != 200:
        return []
    return resp.json()


def _sources_to_config(rows: list[dict]) -> dict:
    """Convert user_sources rows to sources_config dict."""
    sources: dict[str, list] = {}
    for row in rows:
        stype = row["source_type"]
        if stype not in sources:
            sources[stype] = []
        entry = dict(row.get("config") or {})
        entry["name"] = row["name"]
        if row.get("tags"):
            entry["tags"] = row["tags"]
        sources[stype].append(entry)
    return {"sources": sources}


# ---------------------------------------------------------------------------
# Explore prompt (self-contained — no config dir access on Vercel)
# ---------------------------------------------------------------------------

EXPLORE_SYSTEM_PROMPT = """\
You are a content source discovery assistant for an AI/tech news aggregator.

Given a list of existing sources the user follows, suggest NEW sources they \
might also enjoy. Focus on creators, channels, and feeds that are similar in \
quality and topic to the existing ones.

## Rules

- Only suggest sources NOT already in the user's list.
- For each suggestion, provide the source type and config fields needed.
- Score relevance_score (0-1) based on how well the source aligns with the \
user's existing sources in terms of quality, depth, and topic overlap.
- In the reason field, explain why this source would be valuable.

Valid source types and their required fields:
- twitter: {handle} — a Twitter/X account handle (without @)
- youtube: {channel_id, name} — a YouTube channel (channel_id starts with UC, 24 chars)
- rss: {url, name} — a direct RSS/Atom feed URL
- rsshub: {route, name} — an RSSHub route (e.g. /some/route)
- arxiv: {url, name} — an arXiv RSS feed URL

Respond with ONLY valid JSON — an array of suggestions:
[
  {
    "source_type": "<type>",
    "name": "<display name>",
    "config": {"<field>": "<value>", ...},
    "tags": ["<tag1>", "<tag2>"],
    "relevance_score": <float 0-1>,
    "reason": "<one sentence>"
  }
]"""


def _summarize_sources(sources_config: dict) -> str:
    lines = []
    sources = sources_config.get("sources", {})
    for stype, entries in sources.items():
        if not entries:
            continue
        for entry in entries:
            if isinstance(entry, dict):
                name = entry.get("name") or entry.get("handle", "")
                tags = entry.get("tags", [])
                if isinstance(tags, str):
                    tags = [t.strip() for t in tags.split(",")]
                tag_str = ", ".join(tags) if tags else ""
                lines.append(f"  [{stype}] {name} (tags: {tag_str})")
    return "\n".join(lines)


def _build_existing_set(sources_config: dict) -> set[str]:
    existing = set()
    sources = sources_config.get("sources", {})
    for entries in sources.values():
        if not entries:
            continue
        for entry in entries:
            if isinstance(entry, dict):
                for key in ("handle", "name", "channel_id", "url", "route"):
                    if key in entry:
                        existing.add(entry[key].lower())
    return existing


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def _validate_youtube(config: dict) -> bool:
    cid = config.get("channel_id", "")
    if not cid or not re.match(r"^UC[\w-]{22}$", cid):
        return False
    try:
        resp = httpx.head(
            f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}",
            follow_redirects=True,
            timeout=10,
        )
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


def _validate_twitter(config: dict) -> bool:
    handle = config.get("handle", "")
    if not handle or not re.match(r"^[A-Za-z0-9_]{1,15}$", handle):
        return False
    try:
        resp = httpx.head(
            f"https://x.com/{handle}",
            follow_redirects=True,
            headers={"User-Agent": _BROWSER_UA},
            timeout=10,
        )
        return resp.status_code != 404
    except httpx.HTTPError:
        return False


def _validate_rss(config: dict) -> bool:
    url = config.get("url", "")
    if not url:
        return False
    try:
        resp = httpx.get(
            url,
            follow_redirects=True,
            headers={"User-Agent": _BROWSER_UA},
            timeout=10,
        )
        if resp.status_code != 200:
            return False
        text = resp.text[:2000]
        return any(tag in text.lower() for tag in ["<rss", "<feed", "<atom", "<?xml"])
    except httpx.HTTPError:
        return False


_VALIDATORS = {
    "youtube": _validate_youtube,
    "twitter": _validate_twitter,
    "rss": _validate_rss,
    "arxiv": _validate_rss,
}


def _validate_suggestions(suggestions: list[dict]) -> list[dict]:
    """Validate suggestions synchronously, filtering out hallucinated ones."""
    results = []
    for s in suggestions:
        source_type = s.get("source_type", "")
        config = s.get("config", {})
        validator = _VALIDATORS.get(source_type)
        if validator is None:
            s["verified"] = None
            results.append(s)
        else:
            try:
                is_valid = validator(config)
                s["verified"] = is_valid
                if is_valid:
                    results.append(s)
            except Exception:
                pass  # Drop on error
    return results


# ---------------------------------------------------------------------------
# Vercel handler
# ---------------------------------------------------------------------------


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}

            # Auth
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

            user = _sb_get_user(supabase_url, supabase_key, jwt)
            if not user or not user.get("id"):
                self._json_response(401, {"error": "Invalid token"})
                return
            user_id = user["id"]

            service_key = os.environ.get("AINEWS_SUPABASE_SERVICE_KEY", "")
            if not service_key:
                self._json_response(500, {"error": "Server misconfigured"})
                return

            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not api_key:
                self._json_response(500, {"error": "ANTHROPIC_API_KEY not configured"})
                return

            # Load user's sources
            rows = _sb_get_sources(supabase_url, service_key, user_id)
            if not rows:
                self._json_response(400, {"error": "No sources configured yet"})
                return
            sources_config = _sources_to_config(rows)

            # Build prompt
            source_type = body.get("source_type")
            limit = min(body.get("limit", 10), 20)
            min_score = body.get("min_score", 0.0)

            summary = _summarize_sources(sources_config)
            type_filter = f"\n\nOnly suggest {source_type} sources." if source_type else ""
            user_prompt = (
                f"Here are the user's current sources:\n{summary}\n"
                f"{type_filter}\nSuggest up to {limit} new sources."
            )

            # Call Claude API
            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 2048,
                    "system": EXPLORE_SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
                timeout=60,
            )
            resp.raise_for_status()
            content = resp.json()["content"][0]["text"]

            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                self._json_response(500, {"error": "Failed to parse LLM response"})
                return

            if isinstance(parsed, dict):
                suggestions = parsed.get("suggestions", parsed.get("sources", []))
            elif isinstance(parsed, list):
                suggestions = parsed
            else:
                suggestions = []

            # Dedup + filter
            existing = _build_existing_set(sources_config)
            results = []
            for s in suggestions:
                if not isinstance(s, dict):
                    continue
                config = s.get("config", {})
                identifiers = [
                    config.get("handle", ""),
                    config.get("channel_id", ""),
                    config.get("url", ""),
                    config.get("route", ""),
                    s.get("name", ""),
                ]
                if any(
                    ident.lower() in existing for ident in identifiers if ident
                ):
                    continue
                score = float(s.get("relevance_score", 0))
                if score < min_score:
                    continue
                results.append(
                    {
                        "source_type": s.get("source_type", "rss"),
                        "name": s.get("name", ""),
                        "config": config,
                        "tags": s.get("tags", []),
                        "relevance_score": round(score, 2),
                        "reason": s.get("reason", ""),
                    }
                )

            results.sort(key=lambda x: x["relevance_score"], reverse=True)

            # Validate against live services
            results = _validate_suggestions(results)

            self._json_response(200, {"suggestions": results[:limit]})

        except httpx.HTTPError as e:
            self._json_response(502, {"error": f"API call failed: {e}"})
        except Exception as e:
            self._json_response(
                500,
                {"error": f"Internal server error: {type(e).__name__}: {e}"},
            )

    def do_OPTIONS(self):
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
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
