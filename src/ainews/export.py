"""Export scored items to JSON for static site deployment."""

import json
from datetime import datetime, timedelta
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

    since = datetime.now() - timedelta(hours=hours)
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
