#!/usr/bin/env python3
"""Sync RSSHUB_URL_MAP in url_constants.py from the RSSHub GitHub repo.

Strategy:
  1. GitHub API (2 calls, needs token for higher limit): get the git tree of
     lib/routes/ to list all .ts file paths at once.
  2. raw.githubusercontent.com (parallel, no auth): fetch file contents cheaply.

Each route .ts file (excluding namespace.ts / *utils* / *types*) contains:
  url: 'www.example.com/path'   → source page URL
  path: '/route-suffix'         → RSSHub path suffix

Full RSSHub route = /<namespace-dir><path>, e.g. /anthropic/news

Set GITHUB_TOKEN env var to raise GitHub API rate limit (5000/hr vs 60/hr).
"""

from __future__ import annotations

import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from url_map_utils import render_map, update_file  # noqa: E402

from ainews.sources.url_constants import OLSHANSK_FEED_MAP  # noqa: E402

RSSHUB_REPO = "DIYgod/RSSHub"
ROUTES_PATH = "lib/routes"
RAW_BASE = f"https://raw.githubusercontent.com/{RSSHUB_REPO}/master"
GH_API = "https://api.github.com"

_BLOCK_START = "# --- BEGIN RSSHUB_URL_MAP (auto-generated) ---"
_BLOCK_END = "# --- END RSSHUB_URL_MAP ---"

_FIELD_RE = re.compile(r"""^\s*(\w+)\s*:\s*['"]([^'"]+)['"]""", re.MULTILINE)

_SKIP_NAMES = {"namespace.ts", "index.ts"}
_SKIP_PATTERNS = ("util", "type", "helper", "common", "base", "api")


def _gh_headers() -> dict[str, str]:
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def get_routes_tree_sha(client: httpx.Client) -> str:
    """Get the git tree SHA for the lib/routes directory."""
    resp = client.get(
        f"{GH_API}/repos/{RSSHUB_REPO}/git/trees/master",
        headers=_gh_headers(),
    )
    resp.raise_for_status()
    tree = resp.json()["tree"]
    lib_sha = next(e["sha"] for e in tree if e["path"] == "lib")

    resp = client.get(
        f"{GH_API}/repos/{RSSHUB_REPO}/git/trees/{lib_sha}",
        headers=_gh_headers(),
    )
    resp.raise_for_status()
    tree = resp.json()["tree"]
    return next(e["sha"] for e in tree if e["path"] == "routes")


def list_route_files(client: httpx.Client, routes_sha: str) -> list[tuple[str, str]]:
    """Return list of (namespace, filename) for all route .ts files."""
    resp = client.get(
        f"{GH_API}/repos/{RSSHUB_REPO}/git/trees/{routes_sha}?recursive=1",
        headers=_gh_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("truncated"):
        print("WARNING: tree response truncated — some routes may be missing", file=sys.stderr)

    result = []
    for entry in data.get("tree", []):
        path = entry.get("path", "")
        parts = path.split("/")
        if len(parts) != 2 or not parts[1].endswith(".ts"):
            continue
        namespace, filename = parts
        if filename in _SKIP_NAMES:
            continue
        if any(p in filename.lower() for p in _SKIP_PATTERNS):
            continue
        result.append((namespace, filename))

    return result


def fetch_raw(client: httpx.Client, namespace: str, filename: str) -> tuple[str, str] | None:
    """Fetch raw content of a route file. Returns (namespace, content) or None."""
    url = f"{RAW_BASE}/{ROUTES_PATH}/{namespace}/{filename}"
    resp = client.get(url)
    if resp.status_code == 404 or not resp.is_success:
        return None
    return namespace, resp.text


def extract_fields(ts_content: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in _FIELD_RE.finditer(ts_content)}


def build_route_map(client: httpx.Client, route_files: list[tuple[str, str]]) -> dict[str, str]:
    """Fetch all route files in parallel and extract url→route mappings."""
    route_map: dict[str, str] = {}
    print(f"Fetching {len(route_files)} route files...", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {pool.submit(fetch_raw, client, ns, fn): (ns, fn) for ns, fn in route_files}
        for future in as_completed(futures):
            result = future.result()
            if not result:
                continue
            namespace, content = result
            fields = extract_fields(content)
            source_url = fields.get("url", "").strip().rstrip("/")
            route_path = fields.get("path", "").strip()
            if not source_url or not route_path or route_path == "/":
                continue
            if ":" in route_path or "*" in route_path:
                continue
            key = re.sub(r"^https?://", "", source_url)
            route_map[key] = f"/{namespace}{route_path}"

    return route_map


def main() -> None:
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        print("Fetching routes tree SHA...", file=sys.stderr)
        routes_sha = get_routes_tree_sha(client)
        print("Listing route files...", file=sys.stderr)
        route_files = list_route_files(client, routes_sha)
        print(f"Found {len(route_files)} route files across all namespaces", file=sys.stderr)
        route_map = build_route_map(client, route_files)

    if not route_map:
        print("ERROR: parsed 0 routes — structure may have changed", file=sys.stderr)
        sys.exit(1)

    overlaps = set(route_map.keys()) & set(OLSHANSK_FEED_MAP.keys())
    if overlaps:
        print(
            f"Note: {len(overlaps)} entries overlap with OLSHANSK_FEED_MAP "
            f"(sync_olshansk_feeds.py will clean those up)",
            file=sys.stderr,
        )

    new_block = render_map(route_map, "RSSHUB_URL_MAP", _BLOCK_START, _BLOCK_END)
    changed = update_file(new_block, _BLOCK_START, _BLOCK_END)

    if changed:
        print(f"Updated RSSHUB_URL_MAP with {len(route_map)} routes.")
    else:
        print(f"No changes — {len(route_map)} routes already up to date.")


if __name__ == "__main__":
    main()
