"""Tests for AI Templates trending ingestion — _component_url, _make_item, fetch."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from ainews.ingest.aitmpl_trending import (
    _component_url,
    _make_item,
    fetch_aitmpl_trending,
)

# --- _component_url ---


def test_component_url_strips_skill_prefix():
    assert _component_url("skill-frontend-design", "skills") == (
        "https://www.aitmpl.com/skills/frontend-design"
    )


def test_component_url_strips_agent_prefix():
    assert _component_url("agent-code-review", "agents") == (
        "https://www.aitmpl.com/agents/code-review"
    )


def test_component_url_strips_mcp_prefix():
    assert _component_url("mcp-filesystem", "mcps") == ("https://www.aitmpl.com/mcps/filesystem")


def test_component_url_no_prefix_keeps_id():
    assert _component_url("custom-thing", "skills") == (
        "https://www.aitmpl.com/skills/custom-thing"
    )


def test_component_url_empty_id():
    assert _component_url("", "skills") == "https://www.aitmpl.com/skills/"


# --- _make_item ---


def _make_test_comp(**overrides):
    base = {
        "id": "skill-test-comp",
        "name": "Test Component",
        "category": "Development",
        "downloadsToday": 50,
        "downloadsWeek": 200,
        "downloadsMonth": 800,
        "downloadsTotal": 5000,
    }
    base.update(overrides)
    return base


def test_make_item_basic():
    today = datetime(2026, 3, 22, tzinfo=timezone.utc)
    comp = _make_test_comp()
    item = _make_item(
        comp,
        rank=1,
        total=10,
        comp_type="skills",
        fragment="all",
        id_prefix="aitmpl",
        source_name="AI Templates Trending",
        source_type="aitmpl_trending",
        today=today,
        tags=["claude-code", "trending"],
    )
    assert item.title == "#1 Test Component"
    assert item.score == 1.0
    assert "skills/test-comp#all" in item.url
    assert "Category: Development" in item.summary
    assert "Today: +50" in item.summary
    assert item.source_name == "AI Templates Trending"
    assert item.tags == ["claude-code", "trending"]


def test_make_item_no_downloads_today_omitted():
    today = datetime(2026, 3, 22, tzinfo=timezone.utc)
    comp = _make_test_comp(downloadsToday=0)
    item = _make_item(
        comp,
        rank=2,
        total=5,
        comp_type="skills",
        fragment="skills",
        id_prefix="aitmpl-detail",
        source_name="AI Templates Trending (skills)",
        source_type="aitmpl_skills",
        today=today,
        tags=[],
    )
    assert "Today:" not in item.summary


def test_make_item_score_rank_3_of_5():
    today = datetime(2026, 3, 22, tzinfo=timezone.utc)
    comp = _make_test_comp()
    item = _make_item(
        comp,
        rank=3,
        total=5,
        comp_type="skills",
        fragment="all",
        id_prefix="aitmpl",
        source_name="src",
        source_type="st",
        today=today,
        tags=[],
    )
    assert item.score == 0.6


def test_make_item_missing_optional_fields():
    today = datetime(2026, 3, 22, tzinfo=timezone.utc)
    comp = {"id": "agent-x", "name": "X"}
    item = _make_item(
        comp,
        rank=1,
        total=1,
        comp_type="agents",
        fragment="all",
        id_prefix="aitmpl",
        source_name="src",
        source_type="st",
        today=today,
        tags=[],
    )
    assert item.title == "#1 X"
    assert "Category: " in item.summary


# --- fetch_aitmpl_trending (mocked HTTP) ---


def _mock_response(payload):
    """Create a mock httpx Response with sync json() and raise_for_status()."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    return resp


def _fake_trending_json(all_items=None, skills_items=None):
    data = {"trending": {}}
    if all_items is not None:
        data["trending"]["all"] = all_items
    if skills_items is not None:
        data["trending"]["skills"] = skills_items
    return data


def _mock_client(resp):
    """Create a mock httpx.AsyncClient that returns resp on .get()."""
    client = AsyncMock()
    client.get.return_value = resp
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def test_fetch_aitmpl_trending_basic():
    async def _run():
        comp = {
            "id": "skill-demo",
            "name": "Demo",
            "category": "Dev",
            "downloadsToday": 10,
            "downloadsWeek": 50,
            "downloadsMonth": 200,
            "downloadsTotal": 1000,
        }
        payload = _fake_trending_json(all_items=[comp])
        resp = _mock_response(payload)
        client = _mock_client(resp)

        with patch("ainews.ingest.aitmpl_trending.httpx.AsyncClient", return_value=client):
            items = await fetch_aitmpl_trending()

        assert len(items) == 1
        assert items[0].title == "#1 Demo"
        assert items[0].score == 1.0

    asyncio.run(_run())


def test_fetch_aitmpl_trending_includes_per_type():
    async def _run():
        comp_all = {"id": "skill-a", "name": "A", "category": "Dev"}
        comp_skills = {"id": "skill-b", "name": "B", "category": "Dev"}
        payload = _fake_trending_json(all_items=[comp_all], skills_items=[comp_skills])
        resp = _mock_response(payload)
        client = _mock_client(resp)

        with patch("ainews.ingest.aitmpl_trending.httpx.AsyncClient", return_value=client):
            items = await fetch_aitmpl_trending()

        assert len(items) == 2
        source_names = {i.source_name for i in items}
        assert "AI Templates Trending" in source_names
        assert "AI Templates Trending (skills)" in source_names

    asyncio.run(_run())


def test_fetch_aitmpl_trending_empty_response():
    async def _run():
        payload = {"trending": {}}
        resp = _mock_response(payload)
        client = _mock_client(resp)

        with patch("ainews.ingest.aitmpl_trending.httpx.AsyncClient", return_value=client):
            items = await fetch_aitmpl_trending()

        assert items == []

    asyncio.run(_run())
