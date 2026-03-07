"""LLM-based content scoring using Claude API (cloud alternative to Ollama)."""

import json
import logging
import os

import httpx

from ainews.models import ContentItem, ScoredItem
from ainews.scoring.scorer import SYSTEM_PROMPT, _build_user_prompt

logger = logging.getLogger(__name__)


async def score_item_claude(
    item: ContentItem,
    principles: dict,
    api_key: str | None = None,
    model: str = "claude-sonnet-4-20250514",
) -> ScoredItem:
    """Score a single content item using the Claude API."""
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is required for Claude scoring")

    prompt = _build_user_prompt(item, principles)

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
                "max_tokens": 256,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()

    body = resp.json()
    content = body["content"][0]["text"]

    try:
        parsed = json.loads(content)
        return ScoredItem(**parsed)
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"Failed to parse Claude response for '{item.title}': {e}")
        return ScoredItem(
            relevance_score=0.5,
            tier="personal",
            reason="Scoring failed — defaulting to neutral",
            key_topics=[],
        )


async def score_batch_claude(
    items: list[ContentItem],
    principles: dict,
    api_key: str | None = None,
    model: str = "claude-sonnet-4-20250514",
) -> list[tuple[ContentItem, ScoredItem]]:
    """Score a batch of items using Claude API."""
    results = []
    for item in items:
        try:
            scored = await score_item_claude(item, principles, api_key, model)
            item.score = scored.relevance_score
            item.score_reason = scored.reason
            item.tier = scored.tier
            results.append((item, scored))
        except Exception:
            logger.exception(f"Failed to score '{item.title}'")
    return results
