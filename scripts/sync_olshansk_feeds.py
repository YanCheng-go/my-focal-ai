#!/usr/bin/env python3
"""Sync OLSHANSK_FEED_MAP in url_constants.py from the Olshansk/rss-feeds README.

Fetches the README, parses the feed→URL table, and rewrites the map in-place.
Run manually or via GitHub Actions cron.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from url_map_utils import render_map, update_file  # noqa: E402

from ainews.sources.url_constants import RSSHUB_URL_MAP  # noqa: E402

README_URL = "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/README.md"
FEEDS_BASE = "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds"

# Matches a markdown table row: | [Name](site_url) | [feed_xxx.xml](raw_url) |
_ROW_RE = re.compile(
    r"\|\s*\[[^\]]+\]\((https?://[^)]+)\)\s*\|\s*\[(feed_[^\]]+\.xml)\]\(https?://[^)]+\)"
)

_BLOCK_START = "# --- BEGIN OLSHANSK_FEED_MAP (auto-generated) ---"
_BLOCK_END = "# --- END OLSHANSK_FEED_MAP ---"


def fetch_readme() -> str:
    resp = httpx.get(README_URL, timeout=15, follow_redirects=True)
    resp.raise_for_status()
    return resp.text


def parse_feed_map(readme: str) -> dict[str, str]:
    """Return {normalized_url_key: raw_feed_url}, excluding entries in RSSHUB_URL_MAP."""
    rsshub_keys = set(RSSHUB_URL_MAP.keys())
    feed_map: dict[str, str] = {}
    for m in _ROW_RE.finditer(readme):
        site_url, filename = m.group(1).rstrip("/"), m.group(2)
        key = re.sub(r"^https?://", "", site_url)
        if key not in rsshub_keys:
            feed_map[key] = f"{FEEDS_BASE}/{filename}"
    return feed_map


def main() -> None:
    readme = fetch_readme()
    feed_map = parse_feed_map(readme)

    if not feed_map:
        print("ERROR: parsed 0 feeds — README format may have changed", file=sys.stderr)
        sys.exit(1)

    new_block = render_map(feed_map, "OLSHANSK_FEED_MAP", _BLOCK_START, _BLOCK_END)
    changed = update_file(new_block, _BLOCK_START, _BLOCK_END)

    if changed:
        print(f"Updated OLSHANSK_FEED_MAP with {len(feed_map)} feeds.")
    else:
        print(f"No changes — {len(feed_map)} feeds already up to date.")


if __name__ == "__main__":
    main()
