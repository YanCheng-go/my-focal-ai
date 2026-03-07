"""CLI entry point."""

import argparse
import asyncio
import logging
import sys

import uvicorn

from ainews.config import Settings


async def _fetch_source(source_name: str):
    """Fetch a single source by name (one-time)."""
    from ainews.config import load_sources
    from ainews.ingest.feeds import build_feed_urls, fetch_feed
    from ainews.ingest.twitter import fetch_twitter_user, get_twitter_cookies_from_browser
    from ainews.storage.db import get_db, ingest_items

    settings = Settings()
    conn = get_db(settings.db_path)
    try:
        sources_config = load_sources(settings.config_dir)

        # Check Twitter handles
        twitter_users = sources_config.get("sources", {}).get("twitter", [])
        for user in twitter_users:
            handle = user["handle"]
            if source_name.lower() in (handle.lower(), f"@{handle}".lower()):
                cookies = get_twitter_cookies_from_browser()
                if not cookies:
                    print("No Twitter cookies found in Chrome. Make sure you're logged into x.com.")
                    return
                items = await fetch_twitter_user(handle, cookies, tags=user.get("tags", []))
                new_count = ingest_items(conn, f"twitter:@{handle}", items)
                print(f"Fetched {len(items)} tweets from @{handle} ({new_count} new)")
                return

        # Check all feed sources
        feeds = build_feed_urls(sources_config)
        matched = [f for f in feeds if source_name.lower() in f["source_name"].lower()]

        if not matched:
            print(f"No source found matching '{source_name}'.")
            print("\nAvailable sources:")
            for f in feeds:
                print(f"  - {f['source_name']}")
            for u in twitter_users:
                print(f"  - @{u['handle']}")
            return

        for feed_meta in matched:
            try:
                items = await fetch_feed(**feed_meta)
                new_count = ingest_items(conn, feed_meta["source_name"], items)
                print(f"Fetched {len(items)} items from {feed_meta['source_name']} ({new_count} new)")
            except Exception as e:
                print(f"Failed to fetch {feed_meta['source_name']}: {e}")
    finally:
        conn.close()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="AI News Filter")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("serve", help="Start the web server with scheduled fetching")
    sub.add_parser("fetch", help="Run a one-time fetch + score cycle")

    fetch_source_parser = sub.add_parser("fetch-source", help="Fetch a single source by name (one-time)")
    fetch_source_parser.add_argument("name", help="Source name or Twitter handle (partial match)")

    sub.add_parser("twitter-setup", help="Set up Twitter scraping from Chrome cookies (one-time)")

    twitter_parser = sub.add_parser("twitter-login", help="Set up Twitter with username/password (one-time)")
    twitter_parser.add_argument("--username", required=True, help="Twitter username")
    twitter_parser.add_argument("--password", required=True, help="Twitter password")
    twitter_parser.add_argument("--email", required=True, help="Email linked to the Twitter account")

    sub.add_parser("list-sources", help="List all configured sources")

    args = parser.parse_args()

    if args.command == "serve":
        settings = Settings()
        uvicorn.run("ainews.api.app:app", host=settings.host, port=settings.port, reload=True)
    elif args.command == "fetch":
        from ainews.api.app import _fetch_and_score
        asyncio.run(_fetch_and_score())
    elif args.command == "fetch-source":
        asyncio.run(_fetch_source(args.name))
    elif args.command == "list-sources":
        from ainews.config import load_sources
        from ainews.ingest.feeds import build_feed_urls
        settings = Settings()
        sources_config = load_sources(settings.config_dir)
        feeds = build_feed_urls(sources_config)
        twitter_users = sources_config.get("sources", {}).get("twitter", [])
        print("Configured sources:")
        for f in feeds:
            print(f"  [{f['source_type']}] {f['source_name']}")
        for u in twitter_users:
            print(f"  [twitter] @{u['handle']}")
    elif args.command == "twitter-setup":
        from ainews.ingest.twitter import setup_twitter_from_cookies
        asyncio.run(setup_twitter_from_cookies())
        print("Twitter set up from Chrome cookies. Tweets will be fetched on next ingestion cycle.")
    elif args.command == "twitter-login":
        from ainews.ingest.twitter import setup_twitter_account
        asyncio.run(setup_twitter_account(args.username, args.password, args.email))
        print("Twitter account set up. Tweets will be fetched on next ingestion cycle.")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
