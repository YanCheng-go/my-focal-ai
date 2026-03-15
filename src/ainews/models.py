"""Core data models."""

import hashlib
from datetime import datetime

from pydantic import BaseModel, Field


def make_id(url: str, user_id: str | None = None) -> str:
    """Generate a short deterministic ID from a URL, scoped by user_id if provided."""
    key = f"{user_id}:{url}" if user_id else url
    return hashlib.sha256(key.encode()).hexdigest()[:16]


class ContentItem(BaseModel):
    """A normalized piece of content from any source."""

    id: str  # hash of url
    url: str
    title: str
    summary: str = ""
    content: str = ""
    source_name: str
    source_type: str  # twitter, youtube, xiaohongshu, rss
    tags: list[str] = Field(default_factory=list)
    author: str = ""
    published_at: datetime | None = None
    fetched_at: datetime = Field(default_factory=datetime.now)

    # Scoring fields (populated after LLM evaluation)
    score: float | None = None
    score_reason: str = ""
    tier: str = ""  # personal, work
    is_duplicate_of: str | None = None  # id of the primary item


class ScoredItem(BaseModel):
    """Result of LLM scoring."""

    relevance_score: float = Field(ge=0, le=1, description="0=noise, 1=must-read")
    tier: str = Field(description="personal or work")
    reason: str = Field(description="One-line explanation citing which principles apply")
    key_topics: list[str] = Field(default_factory=list)
    source_proximity: str = Field(
        default="derivative",
        description="origin, implementation, derivative, or noise",
    )
