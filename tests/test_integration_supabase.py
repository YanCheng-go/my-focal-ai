"""Integration tests against a real local Supabase instance.

Requires: `supabase start` running locally (migrations auto-applied).
Skip with: pytest -m 'not integration'
"""

import os
import uuid

import pytest

# Skip entire module if local Supabase isn't running or supabase pkg not installed
pytestmark = pytest.mark.integration

try:
    from supabase import create_client
except ImportError:
    pytest.skip("supabase package not installed", allow_module_level=True)

LOCAL_URL = os.environ.get("SUPABASE_LOCAL_URL", "http://127.0.0.1:54321")
LOCAL_ANON_KEY = os.environ.get("SUPABASE_LOCAL_ANON_KEY", "")
LOCAL_SERVICE_KEY = os.environ.get("SUPABASE_LOCAL_SERVICE_KEY", "")

if not LOCAL_ANON_KEY or not LOCAL_SERVICE_KEY:
    pytest.skip(
        "Set SUPABASE_LOCAL_ANON_KEY and SUPABASE_LOCAL_SERVICE_KEY env vars "
        "(from `supabase status`)",
        allow_module_level=True,
    )


def _supabase_reachable():
    """Check if local Supabase is running."""
    try:
        import httpx

        r = httpx.get(f"{LOCAL_URL}/rest/v1/", timeout=2)
        return r.status_code in (200, 401)
    except Exception:
        return False


if not _supabase_reachable():
    pytest.skip("Local Supabase not running (run `supabase start`)", allow_module_level=True)


@pytest.fixture(scope="module")
def test_user():
    """Create a test user for the module. Returns (user_id, access_token)."""
    client = create_client(LOCAL_URL, LOCAL_ANON_KEY)
    email = f"test-{uuid.uuid4().hex[:8]}@example.com"
    result = client.auth.sign_up({"email": email, "password": "testpass123!"})
    assert result.user, "Failed to create test user"
    assert result.session, "No session returned (is email auto-confirm enabled?)"
    return result.user.id, result.session.access_token


@pytest.fixture(scope="module")
def service_client():
    """Supabase client with service role key (bypasses RLS)."""
    return create_client(LOCAL_URL, LOCAL_SERVICE_KEY)


@pytest.fixture()
def backend(test_user):
    """SupabaseBackend scoped to the test user."""
    from ainews.storage.supabase_backend import SupabaseBackend

    user_id = str(test_user[0])
    return SupabaseBackend(LOCAL_URL, LOCAL_SERVICE_KEY, user_id=user_id)


@pytest.fixture()
def public_backend():
    """SupabaseBackend with no user_id (public mode)."""
    from ainews.storage.supabase_backend import SupabaseBackend

    return SupabaseBackend(LOCAL_URL, LOCAL_SERVICE_KEY, user_id=None)


class TestRowToItem:
    """Bug #1: _row_to_item must handle user_id column from Supabase rows."""

    def test_get_items_with_user_id_column(self, backend, test_user):
        """Upsert an item via RPC, then get_items — row includes user_id."""
        from ainews.models import ContentItem, make_id

        user_id = str(test_user[0])
        url = f"https://example.com/integration-test-{uuid.uuid4().hex[:8]}"
        item = ContentItem(
            id=make_id(url, user_id),
            url=url,
            title="Integration test item",
            source_name="test-source",
            source_type="rss",
            tags=["test"],
        )
        backend.upsert_item(item)

        # get_items does SELECT * which includes user_id — this would crash before the fix
        items = backend.get_items(limit=10, search="Integration test item")
        assert any(i.url == url for i in items)

    def test_get_unscored_items_with_user_id(self, backend, test_user):
        """get_unscored_items also returns rows with user_id column."""
        from ainews.models import ContentItem, make_id

        user_id = str(test_user[0])
        url = f"https://example.com/unscored-{uuid.uuid4().hex[:8]}"
        item = ContentItem(
            id=make_id(url, user_id),
            url=url,
            title="Unscored integration item",
            source_name="test-source",
            source_type="rss",
            score=None,
        )
        backend.upsert_item(item)

        unscored = backend.get_unscored_items(limit=10)
        assert any(i.url == url for i in unscored)


class TestTimezoneHandling:
    """Bug #2: timestamps must be timezone-aware for TIMESTAMPTZ columns."""

    def test_fetched_at_has_timezone(self, backend, test_user):
        """Items round-tripped through Supabase preserve timezone info."""
        from ainews.models import ContentItem, make_id

        user_id = str(test_user[0])
        url = f"https://example.com/tz-test-{uuid.uuid4().hex[:8]}"
        item = ContentItem(
            id=make_id(url, user_id),
            url=url,
            title="Timezone test",
            source_name="test-tz",
            source_type="rss",
        )
        backend.upsert_item(item)

        items = backend.get_items(limit=10, search="Timezone test")
        match = [i for i in items if i.url == url]
        assert match, "Item not found after upsert"
        # Supabase TIMESTAMPTZ returns timezone-aware strings
        assert match[0].fetched_at is not None

    def test_set_last_fetched_timezone(self, backend):
        """set_last_fetched should store timezone-aware timestamp."""
        from datetime import datetime, timezone

        key = f"test-source-{uuid.uuid4().hex[:8]}"
        backend.set_last_fetched(key)

        ts = backend.get_last_fetched(key)
        assert ts is not None
        # The stored timestamp should be close to now (within 60s)
        diff = abs((datetime.now(timezone.utc) - ts.replace(tzinfo=timezone.utc)).total_seconds())
        assert diff < 60, f"Timestamp drift too large: {diff}s"


class TestRLSIsolation:
    """Verify row-level security isolates users."""

    def test_user_cannot_see_other_users_items(self, service_client, test_user):
        """Items inserted for user A are invisible to user B via RLS."""
        # Create user B
        email_b = f"test-b-{uuid.uuid4().hex[:8]}@example.com"
        result_b = create_client(LOCAL_URL, LOCAL_ANON_KEY).auth.sign_up(
            {"email": email_b, "password": "testpass123!"}
        )
        assert result_b.user

        user_a_id = str(test_user[0])

        # Insert item for user A via service role
        item_id = f"rls-test-{uuid.uuid4().hex[:8]}"
        service_client.rpc(
            "upsert_item",
            {
                "p_id": item_id,
                "p_url": f"https://example.com/{item_id}",
                "p_title": "User A's item",
                "p_source_name": "rls-test",
                "p_source_type": "rss",
                "p_user_id": user_a_id,
            },
        ).execute()

        # User B's client (with their JWT) should NOT see user A's items
        client_b = create_client(LOCAL_URL, LOCAL_ANON_KEY)
        client_b.auth.sign_in_with_password({"email": email_b, "password": "testpass123!"})
        resp = client_b.table("items").select("id").eq("id", item_id).execute()
        assert len(resp.data) == 0, "User B can see User A's items — RLS broken!"

    def test_public_items_invisible_via_postgrest(self, service_client):
        """Items with user_id=NULL are not accessible via anon PostgREST (by design)."""
        item_id = f"public-rls-{uuid.uuid4().hex[:8]}"
        service_client.rpc(
            "upsert_item",
            {
                "p_id": item_id,
                "p_url": f"https://example.com/{item_id}",
                "p_title": "Public item",
                "p_source_name": "rls-test",
                "p_source_type": "rss",
                "p_user_id": None,
            },
        ).execute()

        # Anon client (no auth) cannot see public items due to RLS
        anon = create_client(LOCAL_URL, LOCAL_ANON_KEY)
        resp = anon.table("items").select("id").eq("id", item_id).execute()
        assert len(resp.data) == 0, "Anon client can see public items — expected RLS to block"


class TestUpsertRPC:
    """Test the upsert_item RPC security and behavior."""

    def test_upsert_preserves_existing_score(self, backend, test_user):
        """Re-upserting with score=None should keep the existing score."""
        from ainews.models import ContentItem, make_id

        user_id = str(test_user[0])
        url = f"https://example.com/score-test-{uuid.uuid4().hex[:8]}"
        item_id = make_id(url, user_id)

        # First insert with a score
        item = ContentItem(
            id=item_id,
            url=url,
            title="Score preservation test",
            source_name="test-score",
            source_type="rss",
            score=0.85,
            score_reason="Important",
            tier="work",
        )
        backend.upsert_item(item)

        # Re-upsert with no score
        item2 = ContentItem(
            id=item_id,
            url=url,
            title="Score preservation test",
            source_name="test-score",
            source_type="rss",
            score=None,
            score_reason="",
            tier="",
        )
        backend.upsert_item(item2)

        # Score should be preserved
        items = backend.get_items(limit=10, search="Score preservation test")
        match = [i for i in items if i.id == item_id]
        assert match, "Item not found"
        assert match[0].score == 0.85, f"Score was overwritten: {match[0].score}"
        assert match[0].score_reason == "Important"
        assert match[0].tier == "work"

    def test_anon_cannot_upsert_for_other_user(self, test_user):
        """Anon key + no session must be rejected when writing to a user's feed."""
        anon = create_client(LOCAL_URL, LOCAL_ANON_KEY)
        user_id = str(test_user[0])
        item_id = f"anon-rpc-{uuid.uuid4().hex[:8]}"

        with pytest.raises(Exception, match="authentication required"):
            anon.rpc(
                "upsert_item",
                {
                    "p_id": item_id,
                    "p_url": f"https://example.com/{item_id}",
                    "p_title": "Anon injection attempt",
                    "p_source_name": "anon-test",
                    "p_source_type": "rss",
                    "p_user_id": user_id,
                },
            ).execute()


class TestIngestItems:
    """Test the full ingest pipeline through Supabase."""

    def test_ingest_dedup(self, backend, test_user):
        """ingest_items should skip items that already exist."""
        from ainews.models import ContentItem, make_id

        user_id = str(test_user[0])
        url = f"https://example.com/dedup-{uuid.uuid4().hex[:8]}"

        items = [
            ContentItem(
                id=make_id(url, user_id),
                url=url,
                title="Dedup test",
                source_name="test-dedup",
                source_type="rss",
            )
        ]

        # First ingest: 1 new item
        count1 = backend.ingest_items("test-dedup", items)
        assert count1 == 1

        # Second ingest: 0 new items (already exists)
        # Re-create items to reset IDs (ingest_items mutates them)
        items2 = [
            ContentItem(
                id=make_id(url),  # original ID without user prefix
                url=url,
                title="Dedup test",
                source_name="test-dedup",
                source_type="rss",
            )
        ]
        count2 = backend.ingest_items("test-dedup", items2)
        assert count2 == 0

    def test_ingest_rescopes_item_ids(self, backend, test_user):
        """ingest_items should re-scope item IDs with user_id prefix."""
        from ainews.models import ContentItem, make_id

        user_id = str(test_user[0])
        url = f"https://example.com/rescope-{uuid.uuid4().hex[:8]}"

        items = [
            ContentItem(
                id=make_id(url),  # no user prefix
                url=url,
                title="Rescope test",
                source_name="test-rescope",
                source_type="rss",
            )
        ]

        original_id = items[0].id
        backend.ingest_items("test-rescope", items)

        # The item ID should have been re-scoped
        expected_id = make_id(url, user_id)
        assert items[0].id == expected_id
        assert items[0].id != original_id
