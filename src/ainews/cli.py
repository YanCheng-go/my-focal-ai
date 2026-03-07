"""CLI entry point."""

import argparse
import asyncio
import logging
import sys

import uvicorn

from ainews.config import Settings


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="AI News Filter")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("serve", help="Start the web server with scheduled fetching")
    sub.add_parser("fetch", help="Run a one-time fetch + score cycle")

    sub.add_parser("twitter-setup", help="Set up Twitter scraping from Chrome cookies (one-time)")

    twitter_parser = sub.add_parser("twitter-login", help="Set up Twitter with username/password (one-time)")
    twitter_parser.add_argument("--username", required=True, help="Twitter username")
    twitter_parser.add_argument("--password", required=True, help="Twitter password")
    twitter_parser.add_argument("--email", required=True, help="Email linked to the Twitter account")

    args = parser.parse_args()

    if args.command == "serve":
        settings = Settings()
        uvicorn.run("ainews.api.app:app", host=settings.host, port=settings.port, reload=True)
    elif args.command == "fetch":
        from ainews.api.app import _fetch_and_score
        asyncio.run(_fetch_and_score())
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
