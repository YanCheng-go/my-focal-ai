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

    args = parser.parse_args()

    if args.command == "serve":
        settings = Settings()
        uvicorn.run("ainews.api.app:app", host=settings.host, port=settings.port, reload=True)
    elif args.command == "fetch":
        from ainews.api.app import _fetch_and_score
        asyncio.run(_fetch_and_score())
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
