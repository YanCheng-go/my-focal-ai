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


def _get_stored_hash(conn) -> str | None:
    row = conn.execute(
        "SELECT last_fetched_at FROM source_state WHERE source_key = ?",
        (CONFIG_HASH_KEY,),
    ).fetchone()
    return row["last_fetched_at"] if row else None


def _store_hash(conn, hash_val: str):
    conn.execute(
        """INSERT INTO source_state (source_key, last_fetched_at) VALUES (?, ?)
           ON CONFLICT(source_key) DO UPDATE SET last_fetched_at = excluded.last_fetched_at""",
        (CONFIG_HASH_KEY, hash_val),
    )


def _apply_metadata_updates(
    conn,
    source_map: dict[str, dict],
    dry_run: bool = False,
) -> int:
    """Compare DB items against source_map and update stale tags/source_type.

    Returns number of items that changed (or would change in dry_run mode).
    """
    rows = conn.execute("SELECT id, source_name, source_type, tags FROM items").fetchall()

    updated = 0
    for row in rows:
        item_id = row["id"]
        source_name = row["source_name"]
        config = source_map.get(source_name)
        if config is None:
            continue

        old_tags = json.loads(row["tags"])
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
            if tags_changed:
                conn.execute(
                    "UPDATE items SET tags = ? WHERE id = ?",
                    (json.dumps(new_tags), item_id),
                )
                conn.execute("DELETE FROM item_tags WHERE item_id = ?", (item_id,))
                if new_tags:
                    conn.executemany(
                        "INSERT OR IGNORE INTO item_tags (item_id, tag) VALUES (?, ?)",
                        [(item_id, tag) for tag in new_tags],
                    )
            if type_changed:
                conn.execute(
                    "UPDATE items SET source_type = ? WHERE id = ?",
                    (new_type, item_id),
                )
        updated += 1

    return updated


def sync_source_metadata(
    conn,
    sources_config: dict,
    config_dir: Path | None = None,
) -> int:
    """Re-sync tags and source_type from config to existing DB items.

    Called automatically during ingestion. Skips if sources.yml hasn't changed.
    Returns number of updated items.
    """
    if config_dir:
        current_hash = _hash_sources_file(config_dir)
        stored_hash = _get_stored_hash(conn)
        if current_hash == stored_hash:
            return 0

    source_map = _build_source_map(sources_config)
    updated = _apply_metadata_updates(conn, source_map)

    if config_dir:
        _store_hash(conn, current_hash)

    conn.commit()
    if updated > 0:
        logger.info(f"Backfill: synced metadata on {updated} items")

    return updated


def backfill_tags(dry_run: bool = False):
    """CLI entry point — re-sync tags and source_type from sources.yml."""
    from ainews.storage.db import get_db

    settings = Settings()
    sources_config = load_sources(settings.config_dir)
    source_map = _build_source_map(sources_config)
    conn = get_db(settings.db_path, settings.turso_url, settings.turso_auth_token)

    try:
        updated = _apply_metadata_updates(conn, source_map, dry_run=dry_run)
        if not dry_run and updated > 0:
            conn.commit()
        action = "Would update" if dry_run else "Updated"
        print(f"{action} {updated} items.")
    finally:
        conn.close()
