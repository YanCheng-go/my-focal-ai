"""Daily audio brief — feed top items to NotebookLM, download narrated 2-host mp3.

Phase 1: local mp3 only. Local/self-hosted only (browser automation + Google login;
never CI). See docs/superpowers/specs/2026-06-26-audio-brief-design.md.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ainews.config import Settings
from ainews.models import ContentItem
from ainews.storage.db import get_backend

logger = logging.getLogger(__name__)


def build_source_text(items: list[ContentItem]) -> str:
    """Plain-text source doc for NotebookLM: one block per item.

    NotebookLM writes and voices its own conversational script from this — we
    supply clean source material, not a script. Fail fast on empty input.
    """
    if not items:
        raise ValueError("No items to brief — widen --hours or lower --min-score")

    blocks = []
    for i in items:
        score = f"{i.score:.2f}" if i.score is not None else "n/a"
        lines = [
            f"## {i.title}",
            f"Source: {i.source_name} | Score: {score}",
        ]
        if i.score_reason:
            lines.append(f"Why it matters: {i.score_reason}")
        lines.append(f"Link: {i.url}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def generate_brief(
    hours: int = 24,
    min_score: float = 0.6,
    out_dir: Path | None = None,
) -> Path:
    """Select top items, hand them to NotebookLM, download the audio brief.

    Glue (network + browser); not unit-tested. The NotebookLM client method names
    below are taken from the design spec and are UNVERIFIED against the live
    `notebooklm-py` library (no curated docs; package unofficial). Verify on first
    real run and adjust.
    """
    settings = Settings()
    out_dir = out_dir or settings.audio_out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    with get_backend(settings.db_path) as backend:
        items = backend.get_items(limit=20, min_score=min_score, since=since)

    text = build_source_text(items)  # raises on empty before any browser work
    logger.info("Briefing %d items from the last %dh", len(items), hours)

    # ponytail: lazy import so a missing [audio] extra doesn't break the rest of the CLI.
    try:
        from notebooklm import NotebookLMClient  # type: ignore
    except ImportError as e:
        raise RuntimeError("notebooklm-py not installed. Run: uv sync --extra audio") from e

    date = since.strftime("%Y-%m-%d")
    out_path = out_dir / f"brief-{date}.mp3"

    client = NotebookLMClient.from_storage()
    nb = client.notebooks.create(f"Daily Brief {date}")
    client.sources.add_text(nb.id, text)
    artifact = client.artifacts.generate_audio(nb.id, instructions=settings.audio_instructions)
    client.artifacts.wait_for_completion(nb.id, artifact.task_id)
    client.artifacts.download_audio(nb.id, out_path)

    logger.info("Audio brief saved to %s", out_path)
    return out_path
