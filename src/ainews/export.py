"""Export scored items to JSON for static site deployment."""

import json
from datetime import datetime, timedelta
from pathlib import Path

from ainews.config import Settings, load_sources
from ainews.storage.db import count_items, get_all_tags, get_db, get_items


def export_items(
    output_path: Path,
    hours: int = 48,
    min_score: float | None = None,
) -> int:
    """Export recent scored items to a JSON file for the static dashboard.

    Returns the number of items exported.
    """
    settings = Settings()
    conn = get_db(settings.db_path, settings.turso_url, settings.turso_auth_token)

    since = datetime.now() - timedelta(hours=hours)
    items = get_items(conn, limit=500, since=since, min_score=min_score)

    # Ensure items from lower-volume source types aren't crowded out by arXiv flood
    ensure_types = ["rss", "youtube", "github_trending", "github_trending_history"]
    existing_ids = {item.id for item in items}
    for stype in ensure_types:
        extra = get_items(conn, limit=50, source_type=stype, since=since)
        for item in extra:
            if item.id not in existing_ids:
                items.append(item)
                existing_ids.add(item.id)

    all_tags = get_all_tags(conn)
    total = count_items(conn, since=since, min_score=min_score)
    conn.close()

    data = {
        "exported_at": datetime.now().isoformat(),
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


def _export_config(output_path: Path, settings: Settings):
    """Export leaderboard, event links for static pages."""
    sources_config = load_sources(settings.config_dir)
    sources = sources_config.get("sources", {})
    config = {
        "leaderboard": sources.get("leaderboard", []),
        "event_links": sources.get("event_links", []),
        "show_scores": settings.show_scores,
    }
    with open(output_path, "w") as f:
        json.dump(config, f, indent=2)
