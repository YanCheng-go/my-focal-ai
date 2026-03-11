"""Backfill — re-sync source config (tags, source_type) to existing DB items."""

import hashlib
import json
import logging
from pathlib import Path

from ainews.config import Settings, load_sources
from ainews.ingest.feeds import build_feed_urls

logger = logging.getLogger(__name__)

CONFIG_HASH_KEY = "sources_yml_hash"


def _build_source_map(sources_config: dict) -> dict[str, dict]:
    """Build a mapping of source_name -> {tags, source_type} from config."""
    source_map: dict[str, dict] = {}

    # Feed-based sources (RSS, YouTube, arXiv, RSSHub, Luma, arxiv_queries)
    for feed in build_feed_urls(sources_config):
        source_map[feed["source_name"]] = {
            "tags": feed.get("tags", []),
            "source_type": feed["source_type"],
        }

    # Twitter
    for user in sources_config.get("sources", {}).get("twitter", []):
        source_map[f"@{user['handle']}"] = {
            "tags": user.get("tags", []),
            "source_type": "twitter",
        }

    # Xiaohongshu
    for user in sources_config.get("sources", {}).get("xiaohongshu", []):
        name = user.get("name", user["user_id"])
        source_map[name] = {
            "tags": user.get("tags", []),
            "source_type": "xiaohongshu",
        }

    # Events
    for src in sources_config.get("sources", {}).get("events", []):
        source_map[src["name"]] = {
            "tags": src.get("tags", []),
            "source_type": "events",
        }

    return source_map


def _hash_sources_file(config_dir: Path) -> str:
    """SHA256 hash of sources.yml content."""
    path = config_dir / "sources.yml"
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _apply_metadata_updates(
    backend,
    source_map: dict[str, dict],
    dry_run: bool = False,
) -> int:
    """Compare DB items against source_map and update stale tags/source_type.

    Returns number of items that changed (or would change in dry_run mode).
    """
    rows = backend.get_items_for_backfill()

    updated = 0
    for row in rows:
        item_id = row["id"]
        source_name = row["source_name"]
        config = source_map.get(source_name)
        if config is None:
            continue

        old_tags = json.loads(row["tags"]) if isinstance(row["tags"], str) else row["tags"]
        new_tags = config["tags"]
        old_type = row["source_type"]
        new_type = config["source_type"]

        tags_changed = sorted(old_tags) != sorted(new_tags)
        type_changed = old_type != new_type

        if not tags_changed and not type_changed:
            continue

        if dry_run:
            changes = []
            if tags_changed:
                changes.append(f"tags: {old_tags} -> {new_tags}")
            if type_changed:
                changes.append(f"type: {old_type} -> {new_type}")
            print(f"  {source_name}: {', '.join(changes)}")
        else:
            backend.update_item_metadata(item_id, new_tags, new_type)
        updated += 1

    return updated


def sync_source_metadata(
    backend,
    sources_config: dict,
    config_dir: Path | None = None,
) -> int:
    """Re-sync tags and source_type from config to existing DB items.

    Called automatically during ingestion. Skips if sources.yml hasn't changed.
    Returns number of updated items.
    """
    if config_dir:
        current_hash = _hash_sources_file(config_dir)
        stored_hash = backend.get_stored_hash(CONFIG_HASH_KEY)
        if current_hash == stored_hash:
            return 0

    source_map = _build_source_map(sources_config)
    updated = _apply_metadata_updates(backend, source_map)

    if config_dir:
        backend.store_hash(CONFIG_HASH_KEY, current_hash)

    backend.commit()
    if updated > 0:
        logger.info(f"Backfill: synced metadata on {updated} items")

    return updated


def backfill_tags(dry_run: bool = False):
    """CLI entry point — re-sync tags and source_type from sources.yml."""
    from ainews.storage.db import get_backend

    settings = Settings()
    sources_config = load_sources(settings.config_dir)
    source_map = _build_source_map(sources_config)
    backend = get_backend(settings.db_path)

    try:
        updated = _apply_metadata_updates(backend, source_map, dry_run=dry_run)
        if not dry_run and updated > 0:
            backend.commit()
        action = "Would update" if dry_run else "Updated"
        print(f"{action} {updated} items.")
    finally:
        backend.close()
