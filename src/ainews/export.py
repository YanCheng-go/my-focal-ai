"""Export scored items to JSON for static site deployment."""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ainews.config import Settings, load_sources
from ainews.storage.db import get_backend

logger = logging.getLogger(__name__)


def _parse_iso(value: str) -> datetime | None:
    """Parse an ISO 8601 datetime string, returning None on failure."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _load_existing_items(path: Path, since: datetime) -> list[dict]:
    """Load items from an existing data.json, filtering to the time window."""
    if not path.exists():
        return []
    try:
        with open(path) as f:
            data = json.load(f)
        items = data.get("items", [])
        result = []
        for item in items:
            dt = _parse_iso(item.get("published_at") or item.get("fetched_at", ""))
            if dt and dt >= since:
                result.append(item)
        return result
    except (json.JSONDecodeError, KeyError):
        logger.warning("Could not read existing %s, skipping merge", path)
        return []


def export_items(
    output_path: Path,
    hours: int = 48,
    min_score: float | None = None,
) -> int:
    """Export recent scored items to a JSON file for the static dashboard.

    Merges with items from the existing data.json so that cloud-fetched items
    (from GitHub Actions) are preserved when the local pipeline exports.

    Returns the number of items exported.
    """
    settings = Settings()
    backend = get_backend(settings.db_path)

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    items = backend.get_items(limit=500, since=since, min_score=min_score)

    # Ensure items from lower-volume source types aren't crowded out by arXiv flood
    ensure_types = [
        "rss",
        "youtube",
        "xiaohongshu",
        "rsshub",
        "github_trending",
        "github_trending_history",
    ]
    existing_ids = {item.id for item in items}
    for stype in ensure_types:
        extra = backend.get_items(limit=50, source_type=stype, since=since)
        for item in extra:
            if item.id not in existing_ids:
                items.append(item)
                existing_ids.add(item.id)

    all_tags = backend.get_all_tags()
    backend.close()

    # Merge: preserve items from existing data.json that aren't in the local DB.
    # This keeps items from the other pipeline when one side overwrites data.json.
    # URL-only dedup is sufficient — local-push.sh only appends Twitter, so there
    # is no overlap between what it writes and what CI writes.
    seen_urls = {item.url for item in items}
    old_items = _load_existing_items(output_path, since)
    old_kept = []
    for old in old_items:
        old_url = old.get("url", "")
        if old_url and old_url not in seen_urls:
            seen_urls.add(old_url)
            old_kept.append(old)

    if old_kept:
        logger.info("Merged %d items from existing data.json", len(old_kept))

    serialized_items = [item.model_dump(mode="json") for item in items] + old_kept

    data = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "period_hours": hours,
        "total": len(serialized_items),
        "all_tags": all_tags,
        "items": serialized_items,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2, default=str)

    # Also export config.json with static page data (leaderboard, event links)
    _export_config(output_path.parent / "config.json", settings)

    return len(serialized_items)


def append_source_type(
    output_path: Path,
    source_type: str,
    hours: int = 168,
) -> int:
    """Append new items of a single source type to an existing data.json.

    Used by local-push.sh to add Twitter items without touching anything else.
    Items already present in the file (by URL) are skipped.
    Returns the number of new items appended.
    """
    settings = Settings()

    # Always regenerate config.json — picks up sources.yml changes even if no new items
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _export_config(output_path.parent / "config.json", settings)

    with get_backend(settings.db_path) as backend:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        new_items = backend.get_items(limit=500, source_type=source_type, since=since)

    # Load existing data.json
    existing = {}
    if output_path.exists():
        try:
            with open(output_path) as f:
                existing = json.load(f)
        except (json.JSONDecodeError, KeyError):
            logger.warning("Could not read %s, will overwrite", output_path)

    existing_items = existing.get("items", [])
    existing_urls = {i.get("url") for i in existing_items}
    to_append = [i for i in new_items if i.url not in existing_urls]

    if not to_append:
        return 0

    all_items = existing_items + [i.model_dump(mode="json") for i in to_append]
    existing["exported_at"] = datetime.now(timezone.utc).isoformat()
    existing["total"] = len(all_items)
    existing["items"] = all_items

    with open(output_path, "w") as f:
        json.dump(existing, f, indent=2, default=str)

    logger.info("Appended %d new %s items to %s", len(to_append), source_type, output_path)
    return len(to_append)


HIDDEN_SOURCE_TYPES = ["events", "luma", "github_trending", "github_trending_history"]
HIDDEN_SOURCES = ["Claude Code Releases"]

# Source type definitions for the admin UI (fields, colors, labels)
SOURCE_TYPE_SCHEMA = {
    "rss": {
        "label": "RSS",
        "aliases": ["rsshub"],
        "fields": {"required": ["url", "name"], "optional": ["display_type", "tags"]},
        "color": "bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-400",
    },
    "youtube": {
        "label": "YouTube",
        "fields": {"required": ["channel_id", "name"], "optional": ["display_type", "tags"]},
        "color": "bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-400",
    },
    "twitter": {
        "label": "Twitter",
        "fields": {"required": ["handle"], "optional": ["display_type", "tags"]},
        "color": "bg-sky-100 text-sky-700 dark:bg-sky-900/50 dark:text-sky-400",
    },
    "arxiv": {
        "label": "ArXiv",
        "aliases": ["arxiv_queries"],
        "fields": {"required": ["url", "name"], "optional": ["display_type", "tags"]},
        "color": "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/50 dark:text-yellow-400",
    },
    "rsshub": {
        "label": "RSSHub",
        "fields": {"required": ["route", "name"], "optional": ["display_type", "tags"]},
        "color": "bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-400",
    },
    "luma": {
        "label": "Luma",
        "fields": {"required": ["handle"], "optional": ["display_type", "tags"]},
        "color": "bg-purple-100 text-purple-700 dark:bg-purple-900/50 dark:text-purple-400",
    },
    "events": {
        "label": "Events",
        "fields": {"required": ["scraper", "name"], "optional": ["display_type", "tags"]},
        "color": "bg-violet-100 text-violet-700 dark:bg-violet-900/50 dark:text-violet-400",
    },
    "arxiv_queries": {
        "label": "ArXiv Query",
        "fields": {"required": ["query", "name"], "optional": ["tags"]},
        "color": "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/50 dark:text-yellow-400",
    },
}


# Source types that work in online mode (serverless fetch via RSS/Atom)
_ONLINE_SOURCE_TYPES = {"rss", "youtube", "arxiv", "arxiv_queries", "rsshub"}


def _config_keys_for(stype: str) -> list[str]:
    """Derive config keys from SOURCE_TYPE_SCHEMA (required fields minus 'name')."""
    schema = SOURCE_TYPE_SCHEMA.get(stype)
    if not schema:
        return []
    fields = schema.get("fields", {})
    return [
        f
        for f in fields.get("required", []) + fields.get("optional", [])
        if f not in ("name", "tags")
    ]


def _build_default_user_sources(sources: dict) -> list[dict]:
    """Convert sources.yml entries to user_sources format for online mode."""
    defaults = []
    for stype, entries in sources.items():
        if stype not in _ONLINE_SOURCE_TYPES or not isinstance(entries, list):
            continue
        keys = _config_keys_for(stype)
        for entry in entries:
            config = {k: entry[k] for k in keys if k in entry}
            defaults.append(
                {
                    "source_type": stype,
                    "name": entry.get("name", ""),
                    "config": config,
                    "tags": entry.get("tags", []),
                }
            )
    return defaults


def _export_config(output_path: Path, settings: Settings):
    """Export leaderboard, event links, and Supabase config for static pages."""
    sources_config = load_sources(settings.config_dir)
    sources = sources_config.get("sources", {})
    config = {
        "leaderboard": sources.get("leaderboard", []),
        "event_links": sources.get("event_links", []),
        "show_scores": settings.show_scores,
        "hidden_source_types": HIDDEN_SOURCE_TYPES,
        "hidden_sources": HIDDEN_SOURCES,
        "source_type_schema": SOURCE_TYPE_SCHEMA,
        "default_user_sources": _build_default_user_sources(sources),
    }
    # Include Supabase config for static admin page auth
    if settings.supabase_url and settings.supabase_key:
        config["supabase_url"] = settings.supabase_url
        config["supabase_anon_key"] = settings.supabase_key
    with open(output_path, "w") as f:
        json.dump(config, f, indent=2)
