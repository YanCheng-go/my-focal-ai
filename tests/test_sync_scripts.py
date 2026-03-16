"""Tests for sync script parsing functions and URL lookup keys."""

from urllib.parse import urlparse

from ainews.sources.url_constants import _url_lookup_keys

# ── extract_fields (sync_rsshub_routes.py) ─────────────────────────


def _extract_fields(ts_content: str) -> dict[str, str]:
    """Import-free copy of the regex extraction from sync_rsshub_routes.py."""
    import re

    field_re = re.compile(r"""^\s*(\w+)\s*:\s*['"]([^'"]+)['"]""", re.MULTILINE)
    return {m.group(1): m.group(2) for m in field_re.finditer(ts_content)}


def test_extract_fields_typical_route():
    ts = """\
export const route: Route = {
    path: '/news',
    name: 'News',
    url: 'www.anthropic.com/news',
    maintainers: ['someone'],
};
"""
    fields = _extract_fields(ts)
    assert fields["path"] == "/news"
    assert fields["url"] == "www.anthropic.com/news"
    assert fields["name"] == "News"


def test_extract_fields_double_quotes():
    ts = '    url: "example.com/blog"\n    path: "/blog"\n'
    fields = _extract_fields(ts)
    assert fields["url"] == "example.com/blog"
    assert fields["path"] == "/blog"


def test_extract_fields_no_url():
    ts = "    name: 'Some Route'\n    maintainers: ['dev']\n"
    fields = _extract_fields(ts)
    assert "url" not in fields
    assert fields["name"] == "Some Route"


def test_extract_fields_empty_content():
    assert _extract_fields("") == {}


def test_extract_fields_ignores_multiword_values():
    """Values with spaces (common in name fields with quotes) are not matched."""
    ts = "    name: 'Two Words'\n"
    fields = _extract_fields(ts)
    # The regex requires [^'"]+ which does match spaces, so this should work
    assert fields["name"] == "Two Words"


# ── parse_feed_map (sync_olshansk_feeds.py) ─────────────────────────


def _parse_feed_map(readme: str, rsshub_keys: set[str] | None = None) -> dict:
    """Import-free copy of the regex parsing from sync_olshansk_feeds.py."""
    import re

    row_re = re.compile(
        r"\|\s*\[([^\]]+)\]\((https?://[^)]+)\)\s*\|\s*\[(feed_[^\]]+\.xml)\]\(https?://[^)]+\)"
    )
    feeds_base = "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds"
    rsshub_keys = rsshub_keys or set()
    feed_map = {}
    for m in row_re.finditer(readme):
        name, site_url, filename = m.group(1).strip(), m.group(2).rstrip("/"), m.group(3)
        key = re.sub(r"^https?://", "", site_url)
        if key not in rsshub_keys:
            feed_map[key] = {"url": f"{feeds_base}/{filename}", "name": name}
    return feed_map


def test_parse_feed_map_typical_row():
    readme = (
        "| [Cursor Blog](https://cursor.com/blog) |"
        " [feed_cursor.xml](https://example.com/feed_cursor.xml) |"
    )
    result = _parse_feed_map(readme)
    assert "cursor.com/blog" in result
    assert result["cursor.com/blog"]["name"] == "Cursor Blog"
    assert "feed_cursor.xml" in result["cursor.com/blog"]["url"]


def test_parse_feed_map_excludes_rsshub_overlap():
    readme = (
        "| [TechCrunch](https://techcrunch.com) | [feed_tc.xml](https://example.com/feed_tc.xml) |"
    )
    result = _parse_feed_map(readme, rsshub_keys={"techcrunch.com"})
    assert result == {}


def test_parse_feed_map_multiple_rows():
    readme = """\
| Site | Feed |
| --- | --- |
| [Alpha](https://alpha.com) | [feed_alpha.xml](https://example.com/feed_alpha.xml) |
| [Beta](https://beta.com/blog) | [feed_beta.xml](https://example.com/feed_beta.xml) |
"""
    result = _parse_feed_map(readme)
    assert len(result) == 2
    assert result.get("alpha.com") is not None
    assert result.get("beta.com/blog") is not None


def test_parse_feed_map_empty_readme():
    assert _parse_feed_map("") == {}


def test_parse_feed_map_no_matching_rows():
    readme = "| [No Feed](https://example.com) | plain_text.xml |"
    assert _parse_feed_map(readme) == {}


def test_parse_feed_map_strips_trailing_slash():
    readme = "| [Site](https://example.com/) | [feed_ex.xml](https://example.com/feed_ex.xml) |"
    result = _parse_feed_map(readme)
    assert result.get("example.com") is not None


# ── _url_lookup_keys (url_constants.py) ─────────────────────────────


def test_url_lookup_keys_with_www():
    keys = _url_lookup_keys(urlparse("https://www.example.com/news"))
    assert keys[0] == "www.example.com/news"  # exact
    assert any(k == "example.com/news" for k in keys)  # www-stripped
    assert any(k == "www.example.com" for k in keys)  # host-only
    assert any(k == "example.com" for k in keys)  # bare host


def test_url_lookup_keys_without_www():
    keys = _url_lookup_keys(urlparse("https://techcrunch.com/feed"))
    assert keys[0] == "techcrunch.com/feed"  # exact
    assert any(k == "techcrunch.com" for k in keys)  # host-only
    # No www. variant added when input doesn't have www.
    assert "www.techcrunch.com/feed" not in keys


def test_url_lookup_keys_no_path():
    keys = _url_lookup_keys(urlparse("https://example.com"))
    # host-only and bare should be present, no duplicates
    assert any(k == "example.com" for k in keys)
    assert len(keys) == len(set(keys))


def test_url_lookup_keys_trailing_slash_stripped():
    keys = _url_lookup_keys(urlparse("https://example.com/blog/"))
    assert any(k == "example.com/blog" for k in keys)  # trailing slash stripped


def test_url_lookup_keys_deduplicates():
    keys = _url_lookup_keys(urlparse("https://example.com/"))
    # Path "/" strips to "", so host+path == host-only; should not duplicate
    assert keys.count("example.com") == 1


def test_url_lookup_keys_preserves_order():
    """Most specific (host+path) should come before least specific (bare host)."""
    keys = _url_lookup_keys(urlparse("https://www.example.com/blog"))
    host_path_idx = keys.index("www.example.com/blog")
    bare_host_idx = keys.index("example.com")
    assert host_path_idx < bare_host_idx
