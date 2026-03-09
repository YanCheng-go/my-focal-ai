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
    from ainews.ingest.runner import fetch_single_source
    from ainews.storage.db import get_db

    settings = Settings()
    conn = get_db(settings.db_path)
    try:
        sources_config = load_sources(settings.config_dir)
        result = await fetch_single_source(conn, sources_config, source_name)
        print(f"Fetched {result['items_fetched']} items ({result['new_items']} new)")
    except (ValueError, RuntimeError) as e:
        print(str(e))
    finally:
        conn.close()


def main():
    log_fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    logging.basicConfig(level=logging.INFO, format=log_fmt)
    parser = argparse.ArgumentParser(description="AI News Filter")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("serve", help="Start the web server with scheduled fetching")
    sub.add_parser("fetch", help="Run a one-time fetch + score cycle")

    fetch_source_parser = sub.add_parser(
        "fetch-source",
        help="Fetch a single source by name (one-time)",
    )
    fetch_source_parser.add_argument("name", help="Source name or Twitter handle (partial match)")

    sub.add_parser("twitter-setup", help="Set up Twitter scraping from Chrome cookies (one-time)")

    twitter_parser = sub.add_parser(
        "twitter-login",
        help="Set up Twitter with username/password (one-time)",
    )
    twitter_parser.add_argument("--username", required=True, help="Twitter username")
    twitter_parser.add_argument("--password", required=True, help="Twitter password")
    twitter_parser.add_argument(
        "--email",
        required=True,
        help="Email linked to the Twitter account",
    )

    sub.add_parser("list-sources", help="List all configured sources")

    sub.add_parser(
        "cloud-fetch",
        help="Fetch feeds + score with Claude API (for CI, no Twitter/Ollama)",
    )

    export_parser = sub.add_parser("export", help="Export scored items to JSON for static site")
    export_parser.add_argument(
        "--hours", type=int, default=48, help="Export items from the last N hours (default: 48)"
    )
    export_parser.add_argument(
        "--output",
        type=str,
        default="static/data.json",
        help="Output path (default: static/data.json)",
    )
    export_parser.add_argument("--min-score", type=float, default=None, help="Minimum score filter")

    backfill_parser = sub.add_parser(
        "backfill-tags",
        help="Re-sync tags from sources.yml config to existing DB items",
    )
    backfill_parser.add_argument(
        "--dry-run", action="store_true", help="Show what would change without modifying the DB"
    )

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
        xhs_users = sources_config.get("sources", {}).get("xiaohongshu", [])
        print("Configured sources:")
        for f in feeds:
            print(f"  [{f['source_type']}] {f['source_name']}")
        for u in twitter_users:
            print(f"  [twitter] @{u['handle']}")
        for u in xhs_users:
            print(f"  [xiaohongshu] {u.get('name', u['user_id'])}")
    elif args.command == "twitter-setup":
        from ainews.ingest.twitter import setup_twitter_from_cookies

        asyncio.run(setup_twitter_from_cookies())
        print("Twitter set up from Chrome cookies. Tweets will be fetched on next ingestion cycle.")
    elif args.command == "twitter-login":
        from ainews.ingest.twitter import setup_twitter_account

        asyncio.run(setup_twitter_account(args.username, args.password, args.email))
        print("Twitter account set up. Tweets will be fetched on next ingestion cycle.")
    elif args.command == "cloud-fetch":
        from ainews.cloud_fetch import cloud_fetch_and_score

        asyncio.run(cloud_fetch_and_score())
    elif args.command == "backfill-tags":
        from ainews.backfill import backfill_tags

        backfill_tags(dry_run=args.dry_run)
    elif args.command == "export":
        from pathlib import Path

        from ainews.export import export_items

        output = Path(args.output)
        count = export_items(output, hours=args.hours, min_score=args.min_score)
        print(f"Exported {count} items to {output}")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
