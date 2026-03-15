"""Tests for GitHub trending ingestion — HTML/JSON parsing."""

import json

from ainews.ingest.github_trending import _extract_repos_from_html


def _wrap_nextjs(data: list[dict]) -> str:
    """Build a minimal Next.js page with embedded initialData."""
    escaped = json.dumps(data).replace('"', '\\"')
    return f'<script>self.__next_f.push([1,"\\"initialData\\":{escaped}"])</script>'


# --- _extract_repos_from_html ---


def test_extract_single_repo():
    data = [{"full_name": "user/repo", "repository_description": "A test repo", "rank": 1}]
    html = _wrap_nextjs(data)
    repos = _extract_repos_from_html(html)
    assert len(repos) == 1
    assert repos[0]["full_name"] == "user/repo"
    assert repos[0]["description"] == "A test repo"
    assert repos[0]["rank"] == 1


def test_extract_multiple_repos():
    data = [
        {"full_name": "a/first", "rank": 1},
        {"full_name": "b/second", "rank": 2},
    ]
    html = _wrap_nextjs(data)
    repos = _extract_repos_from_html(html)
    assert len(repos) == 2
    assert repos[0]["full_name"] == "a/first"
    assert repos[1]["full_name"] == "b/second"


def test_extract_missing_optional_fields():
    data = [{"full_name": "user/repo"}]
    html = _wrap_nextjs(data)
    repos = _extract_repos_from_html(html)
    assert repos[0]["description"] == ""
    assert repos[0]["stars"] == 0
    assert repos[0]["language"] == ""
    assert repos[0]["rank"] == 0
    assert repos[0]["score"] == 0


def test_extract_skips_objects_without_full_name():
    data = [
        {"some_other_key": "value"},
        {"full_name": "user/repo", "rank": 1},
    ]
    html = _wrap_nextjs(data)
    repos = _extract_repos_from_html(html)
    assert len(repos) == 1
    assert repos[0]["full_name"] == "user/repo"


def test_extract_no_initial_data():
    html = "<html><body>No data here</body></html>"
    repos = _extract_repos_from_html(html)
    assert repos == []


def test_extract_malformed_json():
    html = '<script>self.__next_f.push([1,"\\"initialData\\":[{broken json"])</script>'
    repos = _extract_repos_from_html(html)
    assert repos == []


def test_extract_empty_array():
    html = _wrap_nextjs([])
    repos = _extract_repos_from_html(html)
    assert repos == []


def test_extract_preserves_all_fields():
    data = [
        {
            "full_name": "org/project",
            "repository_description": "Cool project",
            "repository_stars": 42000,
            "repository_language": "Python",
            "rank": 3,
            "score": 95,
        }
    ]
    html = _wrap_nextjs(data)
    repos = _extract_repos_from_html(html)
    assert repos[0]["stars"] == 42000
    assert repos[0]["language"] == "Python"
    assert repos[0]["score"] == 95
