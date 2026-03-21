"""Validate that LLM-suggested sources actually exist.

After the LLM generates source suggestions, this module checks each one
against live services to filter out hallucinated handles, channel IDs,
and feed URLs before presenting results to the user.
"""

import asyncio
import logging
import re

import httpx

from ainews.config import Settings

logger = logging.getLogger(__name__)

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
)
_TIMEOUT = 15


async def _check_youtube(
    config: dict, client: httpx.AsyncClient
) -> bool:
    """Verify a YouTube channel exists by hitting its RSS feed."""
    channel_id = config.get("channel_id", "")
    if not channel_id or not re.match(r"^UC[\w-]{22}$", channel_id):
        return False
    url = (
        f"https://www.youtube.com/feeds/videos.xml"
        f"?channel_id={channel_id}"
    )
    try:
        resp = await client.head(url, follow_redirects=True)
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


async def _check_twitter(
    config: dict, client: httpx.AsyncClient
) -> bool:
    """Verify a Twitter handle exists (non-404 response)."""
    handle = config.get("handle", "")
    if not handle or not re.match(r"^[A-Za-z0-9_]{1,15}$", handle):
        return False
    url = f"https://x.com/{handle}"
    try:
        resp = await client.head(
            url,
            follow_redirects=True,
            headers={"User-Agent": _BROWSER_UA},
        )
        # x.com returns 200 for valid profiles, 404 for non-existent
        return resp.status_code != 404
    except httpx.HTTPError:
        return False


async def _check_rss(
    config: dict, client: httpx.AsyncClient
) -> bool:
    """Verify an RSS/Atom feed URL returns valid XML."""
    url = config.get("url", "")
    if not url:
        return False
    try:
        resp = await client.get(
            url,
            follow_redirects=True,
            headers={"User-Agent": _BROWSER_UA},
        )
        if resp.status_code != 200:
            return False
        # Quick check: does it look like XML/RSS/Atom?
        text = resp.text[:2000]
        return any(
            tag in text.lower()
            for tag in ["<rss", "<feed", "<atom", "<?xml"]
        )
    except httpx.HTTPError:
        return False


async def _check_rsshub(
    config: dict, client: httpx.AsyncClient
) -> bool:
    """Verify an RSSHub route returns valid content."""
    route = config.get("route", "")
    if not route:
        return False
    settings = Settings()
    base = settings.rsshub_base.rstrip("/")
    route = route if route.startswith("/") else f"/{route}"
    url = f"{base}{route}"
    try:
        resp = await client.get(
            url,
            follow_redirects=True,
            headers={"User-Agent": _BROWSER_UA},
        )
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


_VALIDATORS = {
    "youtube": _check_youtube,
    "twitter": _check_twitter,
    "rss": _check_rss,
    "arxiv": _check_rss,  # arXiv feeds are RSS/Atom
    "rsshub": _check_rsshub,
}


async def validate_suggestion(
    suggestion: dict, client: httpx.AsyncClient
) -> dict:
    """Validate a single suggestion. Adds 'verified' field."""
    source_type = suggestion.get("source_type", "")
    config = suggestion.get("config", {})
    validator = _VALIDATORS.get(source_type)

    if validator is None:
        # No validator for this type — mark as unverified but keep it
        suggestion["verified"] = None
        return suggestion

    try:
        is_valid = await validator(config, client)
        suggestion["verified"] = is_valid
    except Exception:
        logger.debug(
            "Validation failed for %s %s",
            source_type,
            suggestion.get("name", ""),
        )
        suggestion["verified"] = False

    return suggestion


async def validate_suggestions(
    suggestions: list[dict],
) -> list[dict]:
    """Validate all suggestions concurrently, filtering out invalid ones.

    Returns only suggestions where verified is True or None (unknown type).
    Each suggestion gets a 'verified' field: True, False, or None.
    """
    if not suggestions:
        return []

    sem = asyncio.Semaphore(5)

    async def _bounded(s: dict, client: httpx.AsyncClient) -> dict:
        async with sem:
            return await validate_suggestion(s, client)

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        results = await asyncio.gather(
            *[_bounded(s, client) for s in suggestions]
        )

    # Keep verified=True and verified=None (unknown type), drop False
    valid = [r for r in results if r["verified"] is not False]
    dropped = len(results) - len(valid)
    if dropped:
        logger.info(
            "Validation dropped %d/%d suggestions (hallucinated)",
            dropped,
            len(results),
        )
    return valid
