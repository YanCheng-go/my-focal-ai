"""LLM-based content scoring using Claude API (cloud alternative to Ollama)."""

import asyncio
import json
import logging
import os

import httpx

from ainews.models import ContentItem, ScoredItem
from ainews.scoring.scorer import SYSTEM_PROMPT, _build_user_prompt

logger = logging.getLogger(__name__)

_MAX_CONCURRENT = 5


async def _score_one(
    client: httpx.AsyncClient,
    item: ContentItem,
    principles: dict,
    api_key: str,
    model: str,
) -> tuple[ContentItem, ScoredItem] | None:
    """Score a single item, returning None on failure."""
    prompt = _build_user_prompt(item, principles)
    try:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 256,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()

        body = resp.json()
        content = body["content"][0]["text"]
        parsed = json.loads(content)
        scored = ScoredItem(**parsed)

        item.score = scored.relevance_score
        item.score_reason = scored.reason
        item.tier = scored.tier
        return (item, scored)
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning(f"Failed to parse Claude response for '{item.title}': {e}")
        scored = ScoredItem(
            relevance_score=0.5,
            tier="personal",
            reason="Scoring failed — defaulting to neutral",
            key_topics=[],
        )
        item.score = scored.relevance_score
        item.score_reason = scored.reason
        item.tier = scored.tier
        return (item, scored)
    except Exception:
        logger.exception(f"Failed to score '{item.title}'")
        return None


async def score_batch_claude(
    items: list[ContentItem],
    principles: dict,
    api_key: str | None = None,
    model: str = "claude-sonnet-4-20250514",
) -> list[tuple[ContentItem, ScoredItem]]:
    """Score a batch of items concurrently using Claude API."""
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is required for Claude scoring")

    sem = asyncio.Semaphore(_MAX_CONCURRENT)

    async def _bounded(item):
        async with sem:
            return await _score_one(client, item, principles, api_key, model)

    async with httpx.AsyncClient(timeout=60) as client:
        results = await asyncio.gather(*[_bounded(item) for item in items])

    return [r for r in results if r is not None]
