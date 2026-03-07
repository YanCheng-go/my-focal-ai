"""Export scored items to JSON for static site deployment."""

import json
from datetime import datetime, timedelta
from pathlib import Path

from ainews.config import Settings
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
    conn = get_db(settings.db_path)

    since = datetime.now() - timedelta(hours=hours)
    items = get_items(conn, limit=500, since=since, min_score=min_score)
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

    return len(items)
