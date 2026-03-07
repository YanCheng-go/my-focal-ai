"""LLM-based content scoring using Ollama."""

import json
import logging

import httpx

from ainews.models import ContentItem, ScoredItem

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a news relevance scorer for an AI/tech practitioner.

Your core test: "Would the user still learn something from this if AI hype disappeared tomorrow?"

You apply three principles IN ORDER:

1. SIGNAL OVER NOISE (Shannon): Does this contain verifiable, new information?
   Signal = reproducible results, specific methods, evidence, code, data
   Noise = vague claims, restated press releases, engagement bait

2. MECHANISM OVER OPINION (First Principles): Does this explain HOW/WHY, not just WHAT?
   Mechanism = explains why something works, discusses tradeoffs and constraints
   Opinion = "this AI is amazing" without reasoning

3. BUILDERS OVER COMMENTATORS (Skin in the Game): Is the author someone who builds or deploys?
   Builders = researchers publishing code, ML engineers, people deploying models
   Commentators = influencers, hype amplifiers, tool reviewers without implementation experience

Information flow model (signal degrades downward):
  Researchers -> Engineers -> Companies -> Influencers -> Media

Stay as close to the source of creation as possible.

Respond with ONLY valid JSON:
{
  "relevance_score": <float 0-1, where 0=noise, 1=must-read>,
  "tier": "<personal|work>",
  "reason": "<one sentence citing which principles apply>",
  "key_topics": ["<topic1>", "<topic2>"],
  "source_proximity": "<origin|implementation|derivative|noise>"
}"""


def _build_user_prompt(item: ContentItem, principles: dict) -> str:
    text = item.content or item.summary or item.title
    if len(text) > 2000:
        text = text[:2000] + "..."

    tiers = principles.get("tiers", {})
    personal = tiers.get("personal", {})
    work = tiers.get("work", {})

    return f"""## Content Item
Title: {item.title}
Source: {item.source_name} ({item.source_type})
Author: {item.author}
Tags: {', '.join(item.tags)}
Text: {text}

## Tier Matching
Personal (weight {personal.get('weight', 1.0)}): {json.dumps(personal.get('focus', []))}
Work (weight {work.get('weight', 0.7)}): {json.dumps(work.get('focus', []))}

Apply the three principles and score this item."""


async def score_item(
    item: ContentItem,
    principles: dict,
    ollama_base_url: str = "http://localhost:11434",
    model: str = "llama3.2",
) -> ScoredItem:
    """Score a single content item using Ollama."""
    prompt = _build_user_prompt(item, principles)

    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"{ollama_base_url}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "format": "json",
            },
        )
        resp.raise_for_status()

    body = resp.json()
    content = body["message"]["content"]

    try:
        parsed = json.loads(content)
        return ScoredItem(**parsed)
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"Failed to parse LLM response for '{item.title}': {e}")
        return ScoredItem(
            relevance_score=0.5,
            tier="personal",
            reason="Scoring failed — defaulting to neutral",
            key_topics=[],
        )


async def score_batch(
    items: list[ContentItem],
    principles: dict,
    ollama_base_url: str = "http://localhost:11434",
    model: str = "llama3.2",
) -> list[tuple[ContentItem, ScoredItem]]:
    """Score a batch of items sequentially (Ollama handles one at a time well)."""
    results = []
    for item in items:
        try:
            scored = await score_item(item, principles, ollama_base_url, model)
            item.score = scored.relevance_score
            item.score_reason = scored.reason
            item.tier = scored.tier
            results.append((item, scored))
        except Exception:
            logger.exception(f"Failed to score '{item.title}'")
    return results
