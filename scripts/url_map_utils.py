"""Shared utilities for sync_rsshub_routes.py and sync_olshansk_feeds.py."""

from __future__ import annotations

import sys
from pathlib import Path

TARGET = Path(__file__).parent.parent / "src/ainews/sources/url_constants.py"


def render_map(url_map: dict[str, str], var_name: str, block_start: str, block_end: str) -> str:
    lines = [block_start, f"{var_name}: dict[str, str] = {{"]
    for key, val in sorted(url_map.items()):
        lines.append(f'    "{key}": "{val}",  # noqa: E501')
    lines += ["}", block_end]
    return "\n".join(lines)


def update_file(new_block: str, block_start: str, block_end: str) -> bool:
    """Replace the auto-generated block in url_constants.py. Returns True if changed."""
    source = TARGET.read_text()
    start = source.find(block_start)
    end = source.find(block_end)
    if start == -1 or end == -1:
        print(f"ERROR: markers not found — expected '{block_start}'", file=sys.stderr)
        sys.exit(1)
    end += len(block_end)
    updated = source[:start] + new_block + source[end:]
    if updated == source:
        return False
    TARGET.write_text(updated)
    return True
