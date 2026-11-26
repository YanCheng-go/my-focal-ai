"""Source exploration mode — discover similar content creators via LLM."""

import json
import logging

import httpx

from ainews.config import Settings, load_principles, load_sources
from ainews.explore_validate import validate_suggestions

logger = logging.getLogger(__name__)

EXPLORE_SYSTEM_PROMPT_TEMPLATE = """\
You are a content source discovery assistant for an AI/tech news aggregator.

Given a list of existing sources the user follows, suggest NEW sources they \
might also enjoy. Focus on creators, channels, and feeds that are similar in \
quality and topic to the existing ones.

## Scoring Principles

Score each suggestion's relevance_score (0-1) based on these principles, \
evaluated IN ORDER:

{principles_text}

## Source Proximity

Prefer sources closer to the origin of information:
{proximity_text}

## Rules

- Only suggest sources NOT already in the user's list.
- For each suggestion, provide the source type and config fields needed.
- The relevance_score MUST reflect how well the source aligns with the \
principles above — not just topical similarity.
- In the reason field, cite which principles the source satisfies.

Valid source types and their required fields:
- twitter: {{handle}} — a Twitter/X account handle (without @)
- youtube: {{channel_id, name}} — a YouTube channel (channel_id starts \
with UC, 24 chars)
- rss: {{url, name}} — a direct RSS/Atom feed URL
- rsshub: {{route, name}} — an RSSHub route (e.g. /some/route)
- arxiv: {{url, name}} — an arXiv RSS feed URL

Respond with ONLY valid JSON — an array of suggestions:
[
  {{
    "source_type": "<type>",
    "name": "<display name>",
    "config": {{"<field>": "<value>", ...}},
    "tags": ["<tag1>", "<tag2>"],
    "relevance_score": <float 0-1>,
    "reason": "<one sentence citing which principles apply>"
  }}
]"""


def _format_principles(principles: dict) -> str:
    """Format principles.yml into text for the system prompt."""
    sections = []
    p = principles.get("principles", {})

    for i, (key, value) in enumerate(p.items(), 1):
        if not isinstance(value, dict):
            continue
        name = value.get("name", key)
        desc = value.get("description", "")
        section = f"{i}. {name}: {desc}"

        indicators = value.get("indicators", {})
        source_trust = value.get("source_trust", {})
        if indicators:
            for label, items in indicators.items():
                if isinstance(items, list):
                    bullet_list = ", ".join(items[:3])
                    section += f"\n   {label}: {bullet_list}"
        if source_trust:
            for label, items in source_trust.items():
                if isinstance(items, list):
                    bullet_list = ", ".join(items[:3])
                    section += f"\n   {label}: {bullet_list}"
        sections.append(section)

    return "\n\n".join(sections)


def _format_proximity(principles: dict) -> str:
    """Format source_proximity tiers into text for the system prompt."""
    proximity = principles.get("source_proximity", {})
    lines = []
    for tier_key, items in proximity.items():
        label = tier_key.replace("_", " ").title()
        if isinstance(items, list):
            examples = ", ".join(items[:2])
            lines.append(f"- {label}: {examples}")
    return "\n".join(lines)


def build_system_prompt(principles: dict) -> str:
    """Build the exploration system prompt with user's principles."""
    principles_text = _format_principles(principles)
    proximity_text = _format_proximity(principles)
    return EXPLORE_SYSTEM_PROMPT_TEMPLATE.format(
        principles_text=principles_text,
        proximity_text=proximity_text,
    )


def _summarize_existing_sources(sources_config: dict) -> str:
    """Build a compact summary of existing sources for the LLM prompt."""
    lines = []
    sources = sources_config.get("sources", {})

    for stype, entries in sources.items():
        if not entries:
            continue
        for entry in entries:
            if isinstance(entry, dict):
                name = entry.get("name") or entry.get("handle", "")
                tags = entry.get("tags", [])
                if isinstance(tags, str):
                    tags = [t.strip() for t in tags.split(",")]
                tag_str = ", ".join(tags) if tags else ""
                lines.append(f"  [{stype}] {name} (tags: {tag_str})")

    return "\n".join(lines)


def _build_existing_set(sources_config: dict) -> set[str]:
    """Build a set of identifiers for existing sources (for dedup)."""
    existing = set()
    sources = sources_config.get("sources", {})
    for entries in sources.values():
        if not entries:
            continue
        for entry in entries:
            if isinstance(entry, dict):
                for key in ("handle", "name", "channel_id", "url", "route"):
                    if key in entry:
                        existing.add(entry[key].lower())
    return existing


def _build_explore_prompt(
    sources_config: dict,
    principles: dict,
    source_type: str | None = None,
    limit: int = 10,
) -> str:
    summary = _summarize_existing_sources(sources_config)
    topic = principles.get("topic", "AI and technology")
    type_filter = ""
    if source_type:
        type_filter = f"\n\nOnly suggest {source_type} sources."

    return f"""Topic of interest: {topic}

Here are the user's current sources:
{summary}
{type_filter}
Suggest up to {limit} new sources the user should follow.
Score each suggestion using the principles provided in the system prompt."""


def _process_suggestions(
    content: str,
    existing: set[str],
    min_score: float,
    limit: int,
    rsshub_base: str,
) -> list[dict]:
    """Parse LLM JSON, dedup, filter by score. Shared by both backends."""
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        logger.warning("Failed to parse LLM response for source exploration")
        return []

    if isinstance(parsed, dict):
        suggestions = parsed.get("suggestions", parsed.get("sources", []))
        if not suggestions and ("name" in parsed or "source_type" in parsed):
            suggestions = [parsed]
    elif isinstance(parsed, list):
        suggestions = parsed
    else:
        return []

    results = []
    for s in suggestions:
        if not isinstance(s, dict):
            continue

        config = s.get("config", {})
        identifiers = [
            config.get("handle", ""),
            config.get("channel_id", ""),
            config.get("url", ""),
            config.get("route", ""),
            s.get("name", ""),
        ]
        if any(ident.lower() in existing for ident in identifiers if ident):
            continue

        score = float(s.get("relevance_score", 0))
        if score < min_score:
            continue

        results.append(
            {
                "source_type": s.get("source_type", "rss"),
                "name": s.get("name", ""),
                "config": config,
                "tags": s.get("tags", []),
                "relevance_score": round(score, 2),
                "reason": s.get("reason", ""),
            }
        )

    results.sort(key=lambda x: x["relevance_score"], reverse=True)
    return results[:limit]


async def explore_sources(
    sources_config: dict | None = None,
    source_type: str | None = None,
    limit: int = 10,
    min_score: float = 0.0,
    ollama_base_url: str | None = None,
    model: str | None = None,
) -> list[dict]:
    """Use LLM to discover new sources similar to existing ones.

    Returns a list of suggestion dicts, each with source_type, name, config,
    tags, relevance_score, and reason. Results are filtered by min_score
    and sorted by relevance_score descending.
    """
    settings = Settings()
    if sources_config is None:
        sources_config = load_sources(settings.config_dir)
    if ollama_base_url is None:
        ollama_base_url = settings.ollama_base_url
    if model is None:
        model = settings.ollama_model

    principles = load_principles(settings.config_dir)
    system_prompt = build_system_prompt(principles)
    prompt = _build_explore_prompt(sources_config, principles, source_type, limit)
    existing = _build_existing_set(sources_config)

    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"{ollama_base_url}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "format": "json",
            },
        )
        resp.raise_for_status()

    content = resp.json()["message"]["content"]
    logger.debug("Explore LLM response: %s", content[:2000])
    results = _process_suggestions(content, existing, min_score, limit, settings.rsshub_base)
    return await validate_suggestions(results, rsshub_base=settings.rsshub_base)


async def explore_sources_claude(
    sources_config: dict | None = None,
    source_type: str | None = None,
    limit: int = 10,
    min_score: float = 0.0,
    api_key: str | None = None,
    model: str = "claude-sonnet-4-20250514",
) -> list[dict]:
    """Use Claude API to discover new sources (cloud alternative to Ollama)."""
    import os

    settings = Settings()
    if sources_config is None:
        sources_config = load_sources(settings.config_dir)
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is required for Claude exploration")

    principles = load_principles(settings.config_dir)
    system_prompt = build_system_prompt(principles)
    prompt = _build_explore_prompt(sources_config, principles, source_type, limit)
    existing = _build_existing_set(sources_config)

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 2048,
                "system": system_prompt,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()

    content = resp.json()["content"][0]["text"]
    results = _process_suggestions(content, existing, min_score, limit, settings.rsshub_base)
    return await validate_suggestions(results, rsshub_base=settings.rsshub_base)
