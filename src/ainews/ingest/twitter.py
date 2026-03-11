"""Twitter ingestion using browser cookies and Twitter's GraphQL API directly."""

import json
import logging
from datetime import datetime

import httpx

from ainews.models import ContentItem, make_id
from ainews.storage.db import ingest_items

logger = logging.getLogger(__name__)

# Twitter web app bearer token (public, embedded in the JS bundle)
BEARER = (  # noqa: E501
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)


def get_twitter_cookies_from_browser() -> dict[str, str] | None:
    """Extract Twitter cookies from Chrome automatically."""
    try:
        import rookiepy

        cookies = rookiepy.chrome(domains=[".x.com", "x.com", ".twitter.com"])
        cookie_dict = {c["name"]: c["value"] for c in cookies}
        if "auth_token" in cookie_dict and "ct0" in cookie_dict:
            return cookie_dict
        logger.warning("Chrome has x.com cookies but missing auth_token or ct0")
    except Exception as e:
        logger.warning(f"Could not read Chrome cookies: {e}")
    return None


def _build_headers(cookies: dict[str, str]) -> dict[str, str]:
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
    return {
        "Authorization": f"Bearer {BEARER}",
        "Cookie": cookie_str,
        "X-Csrf-Token": cookies.get("ct0", ""),
        "X-Twitter-Auth-Type": "OAuth2Session",
        "X-Twitter-Active-User": "yes",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Content-Type": "application/json",
    }


async def fetch_twitter_user(
    handle: str,
    cookies: dict[str, str],
    tags: list[str] | None = None,
    limit: int = 20,
) -> list[ContentItem]:
    """Fetch recent tweets from a user using Twitter's GraphQL API."""
    headers = _build_headers(cookies)

    # Step 1: Get user ID
    variables = json.dumps({"screen_name": handle, "withSafetyModeUserFields": True})
    features = json.dumps(
        {
            "hidden_profile_subscriptions_enabled": True,
            "profile_label_improvements_pcf_label_in_post_enabled": False,
            "rweb_tipjar_consumption_enabled": True,
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "responsive_web_graphql_timeline_navigation_enabled": True,
        }
    )

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            "https://x.com/i/api/graphql/Yka-W8dz7RaEuQNkroPkYw/UserByScreenName",
            params={"variables": variables, "features": features},
            headers=headers,
        )
        if resp.status_code != 200:
            logger.error(f"Twitter UserByScreenName failed for @{handle}: {resp.status_code}")
            return []

        user_data = resp.json()
        try:
            user_id = user_data["data"]["user"]["result"]["rest_id"]
        except (KeyError, TypeError):
            logger.error(f"Could not find user ID for @{handle}")
            return []

        # Step 2: Get user tweets
        variables = json.dumps(
            {
                "userId": user_id,
                "count": limit,
                "includePromotedContent": False,
                "withQuickPromoteEligibilityTweetFields": False,
                "withVoice": False,
                "withV2Timeline": True,
            }
        )
        features = json.dumps(
            {
                "rweb_tipjar_consumption_enabled": True,
                "responsive_web_graphql_exclude_directive_enabled": True,
                "verified_phone_label_enabled": False,
                "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
                "responsive_web_graphql_timeline_navigation_enabled": True,
                "creator_subscriptions_tweet_preview_api_enabled": True,
                "tweetypie_unmention_optimization_enabled": True,
                "responsive_web_edit_tweet_api_enabled": True,
                "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
                "view_counts_everywhere_api_enabled": True,
                "longform_notetweets_consumption_enabled": True,
                "responsive_web_twitter_article_tweet_consumption_enabled": True,
                "tweet_awards_web_tipping_enabled": False,
                "freedom_of_speech_not_reach_fetch_enabled": True,
                "standardized_nudges_misinfo": True,
                "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
                "longform_notetweets_rich_text_read_enabled": True,
                "longform_notetweets_inline_media_enabled": True,
                "responsive_web_enhance_cards_enabled": False,
            }
        )

        resp = await client.get(
            "https://x.com/i/api/graphql/E3opETHurmVJflFsUBVuUQ/UserTweets",
            params={"variables": variables, "features": features},
            headers=headers,
        )
        if resp.status_code != 200:
            logger.error(f"Twitter UserTweets failed for @{handle}: {resp.status_code}")
            return []

    # Parse tweets from the timeline response
    items = []
    try:
        timeline = resp.json()["data"]["user"]["result"]["timeline_v2"]
        instructions = timeline["timeline"]["instructions"]
        for instruction in instructions:
            entries = instruction.get("entries", [])
            for entry in entries:
                try:
                    # Skip promoted/sponsored tweets
                    entry_id = entry.get("entryId", "")
                    item_content = entry.get("content", {}).get("itemContent", {})
                    if entry_id.startswith("promotedTweet-") or item_content.get(
                        "promotedMetadata"
                    ):
                        continue

                    tweet_result = item_content.get("tweet_results", {}).get("result", {})
                    if not tweet_result:
                        continue
                    legacy = tweet_result.get("legacy", {})
                    text = legacy.get("full_text", "")
                    tweet_id = legacy.get("id_str", "")
                    created_at = legacy.get("created_at", "")

                    if not text or not tweet_id:
                        continue

                    # Get actual tweet author — skip retweets from other users
                    actual_author = (
                        tweet_result.get("core", {})
                        .get("user_results", {})
                        .get("result", {})
                        .get("legacy", {})
                        .get("screen_name", handle)
                    )
                    if actual_author.lower() != handle.lower():
                        continue

                    url = f"https://x.com/{actual_author}/status/{tweet_id}"
                    # Dedup by tweet ID, not URL — prevents duplicates across timelines
                    item_id = make_id(f"twitter:{tweet_id}")
                    pub_date = None
                    if created_at:
                        try:
                            pub_date = datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
                        except ValueError:
                            pass

                    items.append(
                        ContentItem(
                            id=item_id,
                            url=url,
                            title=text[:100] + ("..." if len(text) > 100 else ""),
                            summary=text,
                            content=text,
                            source_name=f"@{handle}",
                            source_type="twitter",
                            tags=tags or [],
                            author=handle,
                            published_at=pub_date,
                        )
                    )
                except (KeyError, TypeError):
                    continue
    except (KeyError, TypeError):
        logger.exception(f"Failed to parse tweets for @{handle}")

    return items[:limit]


async def run_twitter_ingestion(conn, sources_config: dict):
    """Fetch all configured Twitter sources."""
    sources = sources_config.get("sources", {})
    twitter_users = sources.get("twitter", [])

    if not twitter_users:
        return 0

    cookies = get_twitter_cookies_from_browser()
    if not cookies:
        logger.warning("No Twitter cookies found in Chrome — skipping Twitter ingestion")
        return 0

    total = 0
    for user in twitter_users:
        handle = user["handle"]
        source_key = f"twitter:@{handle}"
        try:
            items = await fetch_twitter_user(handle, cookies, tags=user.get("tags", []))
            new_count = ingest_items(conn, source_key, items)
            if new_count > 0:
                skipped = len(items) - new_count
                logger.info(f"Fetched {new_count} new tweets from @{handle} ({skipped} skipped)")
            total += new_count
        except Exception:
            logger.exception(f"Failed to fetch @{handle}")

    return total
