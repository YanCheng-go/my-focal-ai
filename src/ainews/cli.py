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
    from ainews.storage.db import get_backend

    settings = Settings()
    backend = get_backend(settings.db_path)
    try:
        sources_config = load_sources(settings.config_dir)
        result = await fetch_single_source(backend, sources_config, source_name)
        print(f"Fetched {result['items_fetched']} items ({result['new_items']} new)")
    except (ValueError, RuntimeError) as e:
        print(str(e))
    finally:
        backend.close()


async def _explore_sources(
    source_type: str | None = None,
    limit: int = 10,
    min_score: float = 0.0,
    cloud: bool = False,
):
    """Run source exploration and print suggestions."""
    if cloud:
        from ainews.explore import explore_sources_claude

        suggestions = await explore_sources_claude(
            source_type=source_type, limit=limit, min_score=min_score
        )
    else:
        from ainews.explore import explore_sources

        suggestions = await explore_sources(
            source_type=source_type, limit=limit, min_score=min_score
        )

    if not suggestions:
        print("No suggestions found. Try different parameters or check your LLM connection.")
        return

    print(f"\nDiscovered {len(suggestions)} source suggestions:\n")
    for i, s in enumerate(suggestions, 1):
        score_bar = "#" * int(s["relevance_score"] * 10)
        print(f"  {i}. [{s['source_type']}] {s['name']}")
        print(f"     Score: {s['relevance_score']:.2f} {score_bar}")
        print(f"     Reason: {s['reason']}")
        if s.get("tags"):
            print(f"     Tags: {', '.join(s['tags'])}")
        print(f"     Config: {s['config']}")
        print()


def main():
    from ainews.config import Settings

    log_fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    level = getattr(logging, Settings().log_level.upper(), logging.INFO)
    logging.basicConfig(level=level, format=log_fmt)
    parser = argparse.ArgumentParser(description="MyFocalAI")
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

    sub.add_parser(
        "fetch-users-twitter",
        help="Fetch Twitter sources for Supabase users locally (requires Chrome cookies)",
    )

    export_parser = sub.add_parser("export", help="Export scored items to JSON for static site")
    export_parser.add_argument(
        "--hours",
        type=int,
        default=None,
        help="Export items from the last N hours (default: AINEWS_EXPORT_HOURS or 168)",
    )
    export_parser.add_argument(
        "--output",
        type=str,
        default="static/data.json",
        help="Output path (default: static/data.json)",
    )
    export_parser.add_argument("--min-score", type=float, default=None, help="Minimum score filter")
    export_parser.add_argument(
        "--source-type",
        type=str,
        default=None,
        help="Only export this source type, appending new items to the existing output file",
    )

    explore_parser = sub.add_parser(
        "explore",
        help="Discover new sources similar to your existing ones (LLM-powered)",
    )
    explore_parser.add_argument(
        "--source-type",
        type=str,
        default=None,
        help="Only suggest sources of this type (e.g. twitter, youtube, rss)",
    )
    explore_parser.add_argument(
        "--limit", type=int, default=10, help="Maximum number of suggestions (default: 10)"
    )
    explore_parser.add_argument(
        "--min-score",
        type=float,
        default=0.0,
        help="Minimum relevance score to include (0-1, default: 0.0)",
    )
    explore_parser.add_argument(
        "--cloud",
        action="store_true",
        help="Use Claude API instead of Ollama for discovery",
    )

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
    elif args.command == "cloud-fetch":
        from ainews.cloud_fetch import cloud_fetch_and_score

        asyncio.run(cloud_fetch_and_score())
    elif args.command == "fetch-users-twitter":
        from ainews.cloud_fetch import local_fetch_user_twitter

        asyncio.run(local_fetch_user_twitter())
    elif args.command == "explore":
        asyncio.run(
            _explore_sources(
                source_type=args.source_type,
                limit=args.limit,
                min_score=args.min_score,
                cloud=args.cloud,
            )
        )
    elif args.command == "backfill-tags":
        from ainews.backfill import backfill_tags

        backfill_tags(dry_run=args.dry_run)
    elif args.command == "export":
        from pathlib import Path

        from ainews.export import append_source_type, export_items

        output = Path(args.output)
        hours = args.hours if args.hours is not None else Settings().export_hours
        if args.source_type:
            count = append_source_type(output, source_type=args.source_type, hours=hours)
            print(f"Appended {count} new {args.source_type} items to {output}")
        else:
            count = export_items(output, hours=hours, min_score=args.min_score)
            print(f"Exported {count} items to {output}")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
