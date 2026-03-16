#!/usr/bin/env python3
"""Sync olshansk_feed_map.json from the Olshansk/rss-feeds README.

Fetches the README, parses the feed->URL table, and writes the JSON file.
Run manually or via GitHub Actions cron.

NOTE: Must run BEFORE sync_rsshub_routes.py so the RSSHub sync can exclude
overlapping entries. The GitHub Actions cron schedules enforce this ordering
(Olshansk at 06:00 UTC, RSSHub at 07:00 UTC).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import httpx

_RSSHUB_MAP = Path(__file__).parent.parent / "src/ainews/sources/rsshub_url_map.json"
_OUTPUT = Path(__file__).parent.parent / "src/ainews/sources/olshansk_feed_map.json"

README_URL = "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/README.md"
FEEDS_BASE = "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds"

# Matches a markdown table row: | [Name](site_url) | [feed_xxx.xml](raw_url) |
_ROW_RE = re.compile(
    r"\|\s*\[[^\]]+\]\((https?://[^)]+)\)\s*\|\s*\[(feed_[^\]]+\.xml)\]\(https?://[^)]+\)"
)


def fetch_readme() -> str:
    resp = httpx.get(README_URL, timeout=15, follow_redirects=True)
    resp.raise_for_status()
    return resp.text


def parse_feed_map(readme: str) -> dict[str, str]:
    """Return {normalized_url_key: raw_feed_url}, excluding entries in RSSHub map."""
    rsshub_keys = set(json.loads(_RSSHUB_MAP.read_text()).keys()) if _RSSHUB_MAP.exists() else set()
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

    new_content = json.dumps(dict(sorted(feed_map.items())), indent=2, ensure_ascii=False) + "\n"
    old_content = _OUTPUT.read_text() if _OUTPUT.exists() else ""

    if new_content == old_content:
        print(f"No changes — {len(feed_map)} feeds already up to date.")
    else:
        _OUTPUT.write_text(new_content)
        print(f"Updated olshansk_feed_map.json with {len(feed_map)} feeds.")


if __name__ == "__main__":
    main()
