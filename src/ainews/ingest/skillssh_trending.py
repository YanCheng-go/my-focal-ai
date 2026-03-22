"""skills.sh trending ingestion — fetches agent skills leaderboard from skills.sh."""

import asyncio
import json
import logging
import re

import httpx

from ainews.ingest import MAX_TRENDING_ITEMS, SCRAPER_HEADERS, rank_to_score, utc_today
from ainews.models import ContentItem, make_id

logger = logging.getLogger(__name__)

SKILLSSH_BASE_URL = "https://skills.sh"
DEFAULT_TAGS = ["agent-skills", "trending", "tools"]

# Pages to fetch — each becomes a source_type
_PAGES = {
    "all": {"path": "/", "source_type": "skillssh_all"},
    "trending": {"path": "/trending", "source_type": "skillssh_trending"},
    "hot": {"path": "/hot", "source_type": "skillssh_hot"},
}

# All page keys (including official and audits) for cleanup
_ALL_PAGE_KEYS = list(_PAGES) + ["official"]


def _extract_initial_skills(html: str) -> list[dict]:
    """Extract initialSkills data from Next.js RSC payload."""
    idx = html.find("initialSkills")
    if idx < 0:
        return []

    # Skip past 'initialSkills\\":'
    rest = html[idx + 16 :]

    # Track bracket depth to find the matching ]
    depth = 0
    end = 0
    for i in range(len(rest)):
        ch = rest[i]
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end == 0:
        return []

    raw = rest[:end]
    # Unescape the double-escaped JSON from RSC payload
    unescaped = raw.replace('\\"', '"')

    try:
        return json.loads(unescaped)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Failed to parse skills.sh initialSkills JSON")
        return []


def _extract_official_owners(html: str) -> list[dict]:
    """Extract official owners data from skills.sh/official RSC payload.

    The data is inside escaped RSC push segments with \\" quoting,
    so we search for the escaped form and unescape before parsing.
    """
    idx = html.find('\\"owners\\"')
    if idx < 0:
        return []

    # Find the enclosing object start
    obj_start = html.rfind("{", max(0, idx - 100), idx)
    if obj_start < 0:
        return []

    # Track brace depth, skipping escaped characters
    depth = 0
    end = obj_start
    i = obj_start
    while i < len(html):
        if html[i : i + 2] == '\\"':
            i += 2
            continue
        if html[i : i + 2] == "\\\\":
            i += 2
            continue
        if html[i] == "{":
            depth += 1
        elif html[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
        i += 1

    raw = html[obj_start:end]
    unescaped = raw.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")

    try:
        data = json.loads(unescaped)
        return data.get("owners", [])
    except (json.JSONDecodeError, ValueError):
        logger.warning("Failed to parse skills.sh official JSON")
        return []


_RE_ENTRY = re.compile(
    r'\{\\"rank\\":(\d+),\\"source\\":\\"([^\\]+)\\",'
    r'\\"skillId\\":\\"([^\\]+)\\",\\"name\\":\\"([^\\]+)\\"'
)
_RE_GEN = re.compile(r'\\"agentTrustHub\\".*?\\"overall_risk_level\\":\\"([^\\]+)\\"')
_RE_SOCKET = re.compile(r'\\"socket\\":\{.*?\\"alerts\\":\[([^\]]*)\]')
_RE_SNYK = re.compile(r'\\"snyk\\":\{.*?\\"overall_risk_level\\":\\"([^\\]+)\\"')


def _extract_audit_entries(html: str) -> list[dict]:
    """Extract audited skills from skills.sh/audits RSC payload.

    The audit data is too large to parse as a single JSON blob (it spans
    multiple RSC push segments), so we use regex to extract individual entries.
    """
    idx = html.find('initialRows\\"')
    if idx < 0:
        return []

    rest = html[idx + 15 :]  # skip 'initialRows\\":'

    matches = list(_RE_ENTRY.finditer(rest))
    if not matches:
        return []

    entries = []
    for i, m in enumerate(matches):
        start = m.start()
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else min(start + 100000, len(rest))
        chunk = rest[start:end_pos]

        gen_match = _RE_GEN.search(chunk)
        socket_match = _RE_SOCKET.search(chunk)
        socket_alerts = len(re.findall(r"\{", socket_match.group(1))) if socket_match else None
        snyk_match = _RE_SNYK.search(chunk)

        entries.append(
            {
                "rank": int(m.group(1)),
                "source": m.group(2),
                "skillId": m.group(3),
                "name": m.group(4),
                "gen": gen_match.group(1) if gen_match else None,
                "socket_alerts": socket_alerts,
                "snyk": snyk_match.group(1) if snyk_match else None,
            }
        )

    return entries


def _skill_url(source: str, skill_id: str) -> str:
    """Build skills.sh URL for a skill."""
    return f"{SKILLSSH_BASE_URL}/{source}/{skill_id}"


async def fetch_skillssh_trending(
    tags: list[str] | None = None,
) -> list[ContentItem]:
    """Fetch trending agent skills from skills.sh (all pages)."""
    today = utc_today()
    default_tags = tags or DEFAULT_TAGS
    all_items: list[ContentItem] = []

    async with httpx.AsyncClient(timeout=30, headers=SCRAPER_HEADERS) as client:
        # Fetch audit data first to enrich trending items
        audit_map: dict[str, dict] = {}  # key: "source/skillId"
        try:
            resp = await client.get(
                f"{SKILLSSH_BASE_URL}/audits",
                follow_redirects=True,
            )
            resp.raise_for_status()
            audit_entries = _extract_audit_entries(resp.text)
            for entry in audit_entries:
                key = f"{entry['source']}/{entry['skillId']}"
                audit_map[key] = entry
            if audit_map:
                logger.info("Loaded %d audit entries from skills.sh", len(audit_map))
        except Exception:
            logger.exception("Failed to fetch skills.sh audits (non-fatal)")

        # Fetch all pages + official concurrently
        async def _fetch_page(url: str) -> httpx.Response | None:
            try:
                resp = await client.get(url, follow_redirects=True)
                resp.raise_for_status()
                return resp
            except Exception:
                logger.exception("Failed to fetch %s", url)
                return None

        page_urls = {k: f"{SKILLSSH_BASE_URL}{v['path']}" for k, v in _PAGES.items()}
        page_urls["official"] = f"{SKILLSSH_BASE_URL}/official"
        responses = await asyncio.gather(
            *(_fetch_page(url) for url in page_urls.values()),
        )
        page_responses = dict(zip(page_urls.keys(), responses))

        for page_key, page_info in _PAGES.items():
            resp = page_responses.get(page_key)
            if not resp:
                continue

            skills = _extract_initial_skills(resp.text)
            if not skills:
                logger.warning("No skills extracted from skills.sh/%s", page_key)
                continue

            for rank, skill in enumerate(skills[:MAX_TRENDING_ITEMS], 1):
                name = skill.get("name", "")
                source = skill.get("source", "")
                installs = skill.get("installs", 0)
                skill_id = skill.get("skillId", name)

                url = _skill_url(source, skill_id)

                summary_parts = [f"Source: {source}"]
                summary_parts.append(f"Installs: {installs:,}")

                # Enrich with audit data if available
                audit_key = f"{source}/{skill_id}"
                audit = audit_map.get(audit_key)
                if audit:
                    gen = audit.get("gen")
                    snyk = audit.get("snyk")
                    s_alerts = audit.get("socket_alerts")
                    if gen:
                        summary_parts.append(f"GEN: {gen}")
                    if s_alerts is not None:
                        summary_parts.append(
                            f"SOCKET: {s_alerts} alert{'s' if s_alerts != 1 else ''}",
                        )
                    if snyk:
                        summary_parts.append(f"SNYK: {snyk}")

                rank_score = rank_to_score(rank, min(len(skills), MAX_TRENDING_ITEMS))

                source_type = page_info["source_type"]
                all_items.append(
                    ContentItem(
                        id=make_id(
                            f"skillssh:{page_key}:{skill_id}:{source}:{today.date()}",
                        ),
                        url=f"{url}#{page_key}",
                        title=f"#{rank} {name}",
                        summary=" | ".join(summary_parts),
                        source_name=f"skills.sh ({page_key})",
                        source_type=source_type,
                        tags=default_tags,
                        published_at=today,
                        score=rank_score,
                    )
                )

            logger.info(
                "Fetched %d skills from skills.sh/%s",
                min(len(skills), MAX_TRENDING_ITEMS),
                page_key,
            )

        # Process official page response
        resp = page_responses.get("official")
        try:
            if not resp:
                raise ValueError("No response")
            owners = _extract_official_owners(resp.text)
            if owners:
                # Flatten to top owners by total installs
                owner_stats = []
                for owner in owners:
                    owner_name = owner.get("owner", "")
                    repos = owner.get("repos", [])
                    total_installs = sum(r.get("totalInstalls", 0) for r in repos)
                    top_skill = ""
                    if repos:
                        all_skills = []
                        for r in repos:
                            all_skills.extend(r.get("skills", []))
                        if all_skills:
                            top_skill = max(
                                all_skills,
                                key=lambda s: s.get("installs", 0),
                            ).get("name", "")
                    owner_stats.append(
                        (owner_name, total_installs, len(repos), top_skill),
                    )

                owner_stats.sort(key=lambda x: x[1], reverse=True)
                top_owners = owner_stats[:MAX_TRENDING_ITEMS]
                for rank, (name, installs, repo_count, top) in enumerate(
                    top_owners,
                    1,
                ):
                    url = f"{SKILLSSH_BASE_URL}/{name}#official"
                    summary_parts = [f"Repos: {repo_count}"]
                    if top:
                        summary_parts.append(f"Top: {top}")
                    summary_parts.append(f"Installs: {installs:,}")

                    rank_score = rank_to_score(rank, len(top_owners))

                    all_items.append(
                        ContentItem(
                            id=make_id(
                                f"skillssh:official:{name}:{today.date()}",
                            ),
                            url=url,
                            title=f"#{rank} {name}",
                            summary=" | ".join(summary_parts),
                            source_name="skills.sh (official)",
                            source_type="skillssh_official",
                            tags=default_tags,
                            published_at=today,
                            score=rank_score,
                        )
                    )
                logger.info(
                    "Fetched %d official owners from skills.sh",
                    len(top_owners),
                )
            else:
                logger.warning("No owners extracted from skills.sh/official")
        except Exception:
            logger.exception("Failed to fetch skills.sh official")

    logger.info(
        "Fetched %d total skills from skills.sh",
        len(all_items),
    )
    return all_items


async def run_skillssh_trending_ingestion(
    backend,
    sources_config: dict,
) -> int:
    """Fetch skills.sh trending data and store new items.

    Trending data is a point-in-time snapshot, so we clear stale items
    before inserting the fresh set.
    """
    sources = sources_config.get("sources", {})
    skillssh_entries = sources.get("skillssh_trending", [])
    if not skillssh_entries:
        return 0

    tags = skillssh_entries[0].get("tags", DEFAULT_TAGS)

    items: list[ContentItem] = []
    try:
        items = await fetch_skillssh_trending(tags=tags)
    except Exception:
        logger.exception("Failed to fetch skills.sh trending")

    if not items:
        return 0

    # Clear all skillssh source types before reinserting
    for page_key in _ALL_PAGE_KEYS:
        backend.delete_source_content(f"skills.sh ({page_key})")

    total_new = backend.ingest_items("skills.sh (all)", items)
    if total_new > 0:
        logger.info("Stored %d trending skills from skills.sh", total_new)

    return total_new
