"""Tests for supabase_manager — sources_to_config conversion."""

from ainews.sources.supabase_manager import get_all_user_ids, sources_to_config


class TestSourcesToConfig:
    def test_empty_rows(self):
        result = sources_to_config([])
        assert result == {"sources": {}}

    def test_single_rss_source(self):
        rows = [
            {
                "source_type": "rss",
                "name": "Hacker News",
                "config": {"url": "https://hnrss.org/frontpage"},
                "tags": ["tech", "news"],
            }
        ]
        result = sources_to_config(rows)
        assert result == {
            "sources": {
                "rss": [
                    {
                        "url": "https://hnrss.org/frontpage",
                        "name": "Hacker News",
                        "tags": ["tech", "news"],
                    }
                ]
            }
        }

    def test_multiple_types(self):
        rows = [
            {
                "source_type": "rss",
                "name": "HN",
                "config": {"url": "https://hn.example.com"},
                "tags": ["tech"],
            },
            {
                "source_type": "youtube",
                "name": "3Blue1Brown",
                "config": {"channel_id": "UCYO_jab_esuFRV4b17AJtAw"},
                "tags": ["math"],
            },
            {
                "source_type": "rss",
                "name": "Lobsters",
                "config": {"url": "https://lobste.rs/rss"},
                "tags": [],
            },
        ]
        result = sources_to_config(rows)
        assert len(result["sources"]["rss"]) == 2
        assert len(result["sources"]["youtube"]) == 1
        assert result["sources"]["youtube"][0]["channel_id"] == "UCYO_jab_esuFRV4b17AJtAw"

    def test_empty_config_and_tags(self):
        rows = [
            {
                "source_type": "twitter",
                "name": "@elonmusk",
                "config": {},
                "tags": None,
            }
        ]
        result = sources_to_config(rows)
        assert result["sources"]["twitter"][0]["name"] == "@elonmusk"
        # No tags key when tags is None
        assert "tags" not in result["sources"]["twitter"][0]


class TestGetAllUserIds:
    def test_deduplicates(self):
        class MockResult:
            data = [
                {"user_id": "aaa"},
                {"user_id": "bbb"},
                {"user_id": "aaa"},
            ]

        class MockQuery:
            def select(self, *a):
                return self

            def eq(self, *a):
                return self

            def execute(self):
                return MockResult()

        class MockClient:
            def table(self, name):
                return MockQuery()

        result = get_all_user_ids(MockClient())
        assert set(result) == {"aaa", "bbb"}
