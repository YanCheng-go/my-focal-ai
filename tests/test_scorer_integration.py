"""Integration tests for scorer — requires local Ollama with a model pulled.

Run with: uv run pytest -m integration tests/test_scorer_integration.py

Configure via env vars:
  AINEWS_OLLAMA_MODEL  (default: gemma3:12b)

To test with a HuggingFace model, pull it into Ollama first:
  ollama pull hf.co/bartowski/Llama-3.2-3B-Instruct-GGUF
  AINEWS_OLLAMA_MODEL=hf.co/bartowski/Llama-3.2-3B-Instruct-GGUF uv run pytest -m integration
"""

import asyncio
import os

import httpx
import pytest

from ainews.models import ContentItem
from ainews.scoring.scorer import score_batch, score_item

pytestmark = pytest.mark.integration


def _run(coro):
    return asyncio.run(coro)


def _item(**kwargs):
    defaults = dict(
        id="test1",
        url="https://example.com",
        title="Test",
        source_name="TestSource",
        source_type="rss",
    )
    defaults.update(kwargs)
    return ContentItem(**defaults)


OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = os.environ.get("AINEWS_OLLAMA_MODEL", "gemma3:12b")


@pytest.fixture
def ollama_available():
    try:
        resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        models = [m["name"] for m in resp.json().get("models", [])]
        if not any(OLLAMA_MODEL in m for m in models):
            pytest.skip(f"Model {OLLAMA_MODEL} not available in Ollama")
    except httpx.ConnectError:
        pytest.skip("Ollama not running")


def test_score_returns_valid_item(ollama_available):
    item = _item(
        title="New transformer architecture reduces inference cost 10x",
        content="Researchers at MIT published a paper showing...",
    )
    scored = _run(score_item(item, {}, OLLAMA_URL, OLLAMA_MODEL))
    assert 0 <= scored.relevance_score <= 1
    assert scored.reason != "Scoring failed — defaulting to neutral"
    assert len(scored.reason) > 0


def test_score_title_only(ollama_available):
    """Minimal item with no content/summary — should still produce a valid score."""
    item = _item(title="Celebrity tweets about AI", content="", summary="")
    scored = _run(score_item(item, {}, OLLAMA_URL, OLLAMA_MODEL))
    assert 0 <= scored.relevance_score <= 1
    assert scored.reason != "Scoring failed — defaulting to neutral"


def test_batch_scores_all(ollama_available):
    items = [
        _item(id="1", title="RLHF improvements paper with code"),
        _item(id="2", title="Someone's opinion about AI hype"),
    ]
    results = _run(score_batch(items, {}, OLLAMA_URL, OLLAMA_MODEL))
    assert len(results) == 2
    for item, scored in results:
        assert 0 <= scored.relevance_score <= 1
        assert scored.reason != "Scoring failed — defaulting to neutral"
