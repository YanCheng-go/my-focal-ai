"""AI Templates trending ingestion — fetches trending Claude Code components from aitmpl.com."""

import logging

import httpx

from ainews.ingest import SCRAPER_HEADERS, rank_to_score, utc_today
from ainews.models import ContentItem, make_id

logger = logging.getLogger(__name__)

AITMPL_TRENDING_URL = "https://www.aitmpl.com/trending-data.json"
AITMPL_BASE_URL = "https://www.aitmpl.com"

DEFAULT_TAGS = ["claude-code", "trending", "tools"]
_ID_PREFIXES = ("skill-", "agent-", "command-", "setting-", "hook-", "mcp-", "template-")
_COMPONENT_TYPES = ("skills", "agents", "commands", "settings", "hooks", "mcps", "templates")


def _component_url(component_id: str, component_type: str) -> str:
    """Build aitmpl.com URL for a component."""
    slug = component_id
    for prefix in _ID_PREFIXES:
        if slug.startswith(prefix):
            slug = slug[len(prefix) :]
            break
    return f"{AITMPL_BASE_URL}/{component_type}/{slug}"


def _make_item(
    comp: dict,
    rank: int,
    total: int,
    comp_type: str,
    fragment: str,
    id_prefix: str,
    source_name: str,
    source_type: str,
    today,
    tags: list[str],
) -> ContentItem:
    comp_id = comp.get("id", "")
    name = comp.get("name", "")
    category = comp.get("category", "")
    today_dl = comp.get("downloadsToday", 0)
    week_dl = comp.get("downloadsWeek", 0)
    month_dl = comp.get("downloadsMonth", 0)
    total_dl = comp.get("downloadsTotal", 0)

    url = f"{_component_url(comp_id, comp_type)}#{fragment}"

    summary_parts = [f"Category: {category}"]
    if today_dl:
        summary_parts.append(f"Today: +{today_dl}")
    summary_parts.append(f"Week: {week_dl:,}")
    summary_parts.append(f"Month: {month_dl:,}")
    summary_parts.append(f"Total: {total_dl:,}")

    return ContentItem(
        id=make_id(f"{id_prefix}:{comp_id}:{today.date()}"),
        url=url,
        title=f"#{rank} {name}",
        summary=" | ".join(summary_parts),
        source_name=source_name,
        source_type=source_type,
        tags=tags,
        published_at=today,
        score=rank_to_score(rank, total),
    )


async def fetch_aitmpl_trending(tags: list[str] | None = None) -> list[ContentItem]:
    """Fetch trending Claude Code components from aitmpl.com."""
    async with httpx.AsyncClient(timeout=30, headers=SCRAPER_HEADERS) as client:
        resp = await client.get(AITMPL_TRENDING_URL, follow_redirects=True)
        resp.raise_for_status()

    data = resp.json()
    trending = data.get("trending", {})
    today = utc_today()
    default_tags = tags or DEFAULT_TAGS

    items = []

    # Combined "all" list (top overall)
    all_components = trending.get("all", [])
    for rank, comp in enumerate(all_components, 1):
        comp_id = comp.get("id", "")
        comp_type = comp_id.split("-", 1)[0] + "s" if "-" in comp_id else ""
        items.append(
            _make_item(
                comp,
                rank,
                len(all_components),
                comp_type,
                "all",
                "aitmpl",
                "AI Templates Trending",
                "aitmpl_trending",
                today,
                default_tags,
            )
        )

    # Per-type top lists
    for comp_type, components in trending.items():
        if comp_type == "all" or not isinstance(components, list):
            continue
        for rank, comp in enumerate(components, 1):
            items.append(
                _make_item(
                    comp,
                    rank,
                    len(components),
                    comp_type,
                    comp_type,
                    "aitmpl-detail",
                    f"AI Templates Trending ({comp_type})",
                    f"aitmpl_{comp_type}",
                    today,
                    default_tags,
                )
            )

    logger.info("Fetched %d trending components from aitmpl.com", len(items))
    return items


async def run_aitmpl_trending_ingestion(backend, sources_config: dict) -> int:
    """Fetch AI Templates trending components and store new items.

    Trending data is a point-in-time snapshot, so we clear stale items
    before inserting the fresh set.
    """
    sources = sources_config.get("sources", {})
    aitmpl_entries = sources.get("aitmpl_trending", [])
    if not aitmpl_entries:
        return 0

    tags = aitmpl_entries[0].get("tags", DEFAULT_TAGS)

    items: list[ContentItem] = []
    try:
        items = await fetch_aitmpl_trending(tags=tags)
    except Exception:
        logger.exception("Failed to fetch AI Templates trending")

    if not items:
        return 0

    # Clear all aitmpl source types before reinserting
    backend.delete_source_content("AI Templates Trending")
    for comp_type in _COMPONENT_TYPES:
        backend.delete_source_content(f"AI Templates Trending ({comp_type})")

    total_new = backend.ingest_items("AI Templates Trending", items)
    if total_new > 0:
        logger.info("Stored %d trending components from aitmpl.com", total_new)

    return total_new
