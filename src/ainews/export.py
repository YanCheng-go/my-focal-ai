"""Export scored items to JSON for static site deployment."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ainews.config import Settings, load_sources
from ainews.storage.db import get_backend


def export_items(
    output_path: Path,
    hours: int = 48,
    min_score: float | None = None,
) -> int:
    """Export recent scored items to a JSON file for the static dashboard.

    Returns the number of items exported.
    """
    settings = Settings()
    backend = get_backend(settings.db_path)

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    items = backend.get_items(limit=500, since=since, min_score=min_score)

    # Ensure items from lower-volume source types aren't crowded out by arXiv flood
    ensure_types = ["rss", "youtube", "github_trending", "github_trending_history"]
    existing_ids = {item.id for item in items}
    for stype in ensure_types:
        extra = backend.get_items(limit=50, source_type=stype, since=since)
        for item in extra:
            if item.id not in existing_ids:
                items.append(item)
                existing_ids.add(item.id)

    all_tags = backend.get_all_tags()
    total = backend.count_items(since=since, min_score=min_score)
    backend.close()

    data = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "period_hours": hours,
        "total": total,
        "all_tags": all_tags,
        "items": [item.model_dump(mode="json") for item in items],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2, default=str)

    # Also export config.json with static page data (leaderboard, event links)
    _export_config(output_path.parent / "config.json", settings)

    return len(items)


HIDDEN_SOURCE_TYPES = ["events", "luma", "github_trending", "github_trending_history"]
HIDDEN_SOURCES = ["Claude Code Releases"]

# Source type definitions for the admin UI (fields, colors, labels)
SOURCE_TYPE_SCHEMA = {
    "rss": {
        "label": "RSS",
        "aliases": ["rsshub"],
        "fields": {"required": ["url", "name"], "optional": ["tags"]},
        "color": "bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-400",
    },
    "youtube": {
        "label": "YouTube",
        "fields": {"required": ["channel_id", "name"], "optional": ["tags"]},
        "color": "bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-400",
    },
    "twitter": {
        "label": "Twitter",
        "fields": {"required": ["handle"], "optional": ["tags"]},
        "color": "bg-sky-100 text-sky-700 dark:bg-sky-900/50 dark:text-sky-400",
    },
    "arxiv": {
        "label": "ArXiv",
        "aliases": ["arxiv_queries"],
        "fields": {"required": ["url", "name"], "optional": ["tags"]},
        "color": "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/50 dark:text-yellow-400",
    },
    "rsshub": {
        "label": "RSSHub",
        "fields": {"required": ["route", "name"], "optional": ["display_type", "tags"]},
        "color": "bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-400",
    },
    "luma": {
        "label": "Luma",
        "fields": {"required": ["handle"], "optional": ["tags"]},
        "color": "bg-purple-100 text-purple-700 dark:bg-purple-900/50 dark:text-purple-400",
    },
    "events": {
        "label": "Events",
        "fields": {"required": ["scraper", "name"], "optional": ["tags"]},
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
