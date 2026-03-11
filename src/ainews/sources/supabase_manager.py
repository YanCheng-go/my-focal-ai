"""Read user_sources from Supabase and convert to sources_config format."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def get_user_sources(client, user_id: str) -> list[dict]:
    """Query user_sources table for a specific user (uses service role, bypasses RLS)."""
    result = (
        client.table("user_sources")
        .select("*")
        .eq("user_id", user_id)
        .eq("disabled", False)
        .execute()
    )
    return result.data or []


def sources_to_config(rows: list[dict]) -> dict:
    """Convert user_sources rows to a sources_config dict matching sources.yml structure.

    Each row has: source_type, name, config (JSONB), tags (JSONB).
    Output: {"sources": {"rss": [...], "youtube": [...], ...}}
    """
    sources: dict[str, list] = {}
    for row in rows:
        stype = row["source_type"]
        if stype not in sources:
            sources[stype] = []

        # Build entry from config JSONB + name + tags
        entry = dict(row.get("config") or {})
        entry["name"] = row["name"]
        if row.get("tags"):
            entry["tags"] = row["tags"]

        sources[stype].append(entry)

    return {"sources": sources}


def get_all_user_ids(client) -> list[str]:
    """Get distinct user_ids that have at least one enabled source."""
    result = client.table("user_sources").select("user_id").eq("disabled", False).execute()
    return list({row["user_id"] for row in (result.data or [])})
