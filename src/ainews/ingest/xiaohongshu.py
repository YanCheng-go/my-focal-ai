"""Xiaohongshu ingestion using browser cookies and XHS web API directly."""

import logging
import sqlite3
from datetime import datetime

import httpx

from ainews.models import ContentItem, make_id
from ainews.storage.db import ingest_items

logger = logging.getLogger(__name__)


def get_xhs_cookies_from_browser() -> dict[str, str] | None:
    """Extract Xiaohongshu cookies from Chrome automatically."""
    try:
        import rookiepy

        cookies = rookiepy.chrome(domains=[".xiaohongshu.com", "xiaohongshu.com"])
        cookie_dict = {c["name"]: c["value"] for c in cookies}
        if "a1" in cookie_dict and "web_session" in cookie_dict:
            return cookie_dict
        logger.warning("Chrome has XHS cookies but missing a1 or web_session")
    except Exception as e:
        logger.warning(f"Could not read Chrome cookies for XHS: {e}")
    return None


def _build_headers(cookies: dict[str, str]) -> dict[str, str]:
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
    return {
        "Cookie": cookie_str,
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Origin": "https://www.xiaohongshu.com",
        "Referer": "https://www.xiaohongshu.com/",
        "Content-Type": "application/json",
    }


async def fetch_xhs_user(
    user_id: str,
    cookies: dict[str, str],
    name: str | None = None,
    tags: list[str] | None = None,
    limit: int = 20,
) -> list[ContentItem]:
    """Fetch recent notes from a Xiaohongshu user via their web API."""
    headers = _build_headers(cookies)
    display_name = name or user_id

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            "https://edith.xiaohongshu.com/api/sns/web/v1/user_posted",
            params={"num": limit, "cursor": "", "user_id": user_id, "image_formats": "jpg"},
            headers=headers,
        )
        if resp.status_code != 200:
            logger.error(f"XHS user_posted failed for {display_name}: {resp.status_code}")
            return []

    body = resp.json()
    if not body.get("success"):
        logger.error(f"XHS API error for {display_name}: {body.get('msg', 'unknown')}")
        return []

    items = []
    notes = body.get("data", {}).get("notes", [])
    for note in notes:
        try:
            note_id = note.get("note_id", "")
            title = note.get("display_title", "")
            if not note_id:
                continue

            url = f"https://www.xiaohongshu.com/explore/{note_id}"
            desc = note.get("desc", "") or title

            pub_date = None
            timestamp = note.get("time")
            if timestamp:
                try:
                    pub_date = datetime.fromtimestamp(timestamp / 1000)
                except (ValueError, TypeError):
                    pass

            items.append(
                ContentItem(
                    id=make_id(url),
                    url=url,
                    title=title or desc[:100],
                    summary=desc,
                    content=desc,
                    source_name=display_name,
                    source_type="xiaohongshu",
                    tags=tags or [],
                    author=note.get("user", {}).get("nickname", ""),
                    published_at=pub_date,
                )
            )
        except (KeyError, TypeError):
            continue

    return items[:limit]


async def run_xhs_ingestion(conn: sqlite3.Connection, sources_config: dict):
    """Fetch all configured Xiaohongshu sources."""
    sources = sources_config.get("sources", {})
    xhs_users = sources.get("xiaohongshu", [])

    if not xhs_users:
        return 0

    cookies = get_xhs_cookies_from_browser()
    if not cookies:
        logger.warning("No XHS cookies found in Chrome — skipping Xiaohongshu ingestion")
        return 0

    total = 0
    for user in xhs_users:
        user_id = user["user_id"]
        source_key = f"xiaohongshu:{user_id}"
        try:
            items = await fetch_xhs_user(
                user_id, cookies, name=user.get("name"), tags=user.get("tags", [])
            )
            new_count = ingest_items(conn, source_key, items)
            if new_count > 0:
                skipped = len(items) - new_count
                logger.info(
                    f"Fetched {new_count} new notes from {user.get('name', user_id)}"
                    f" ({skipped} skipped)"
                )
            total += new_count
        except Exception:
            logger.exception(f"Failed to fetch XHS user {user.get('name', user_id)}")

    return total
