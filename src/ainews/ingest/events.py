"""Event scraping — fetches tech company events from HTML pages."""

import logging
import re
from datetime import datetime, timezone

import httpx
from selectolax.parser import HTMLParser

from ainews.ingest import SCRAPER_HEADERS
from ainews.models import ContentItem, make_id

logger = logging.getLogger(__name__)


async def _fetch_html(url: str) -> str:
    async with httpx.AsyncClient(timeout=30, headers=SCRAPER_HEADERS) as client:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
        return resp.text


def _parse_date_text(text: str) -> datetime | None:
    """Try to parse date strings like 'Apr 22, 2026' or 'March 4 - April 1'."""
    text = text.strip()
    # Try common formats
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    # Try range format — take the first date, e.g. "March 4 - April 1"
    match = re.match(r"(\w+ \d+)", text)
    if match:
        for fmt in ("%B %d", "%b %d"):
            try:
                dt = datetime.strptime(match.group(1), fmt)
                return dt.replace(year=datetime.now(timezone.utc).year, tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


async def fetch_anthropic_events(tags: list[str] | None = None) -> list[ContentItem]:
    """Scrape events from anthropic.com/events (Webflow CMS, server-rendered)."""
    items = []
    base = "https://www.anthropic.com"

    for page_num in (1, 2):
        url = f"{base}/events" if page_num == 1 else f"{base}/events?939688b5_page={page_num}"
        try:
            html = await _fetch_html(url)
        except Exception:
            logger.exception(f"Failed to fetch Anthropic events page {page_num}")
            break

        tree = HTMLParser(html)
        for item_node in tree.css(".event_list_item"):
            name_node = item_node.css_first(".cc-name")
            date_node = item_node.css_first(".cc-date")
            venue_node = item_node.css_first(".cc-venue")
            type_node = item_node.css_first(".cc-type")
            link_node = item_node.css_first("a")

            name = name_node.text(strip=True) if name_node else ""
            if not name:
                continue

            date_text = date_node.text(strip=True) if date_node else ""
            venue = venue_node.text(strip=True) if venue_node else ""
            event_type = type_node.text(strip=True) if type_node else ""

            href = link_node.attributes.get("href", "") if link_node else ""
            if href and not href.startswith("http"):
                href = base + href
            event_url = href or f"{base}/events"

            summary_parts = []
            if event_type:
                summary_parts.append(f"Type: {event_type}")
            if venue:
                summary_parts.append(f"Venue: {venue}")
            if date_text:
                summary_parts.append(f"Date: {date_text}")

            items.append(
                ContentItem(
                    id=make_id(event_url),
                    url=event_url,
                    title=name,
                    summary=". ".join(summary_parts),
                    source_name="Anthropic Events",
                    source_type="events",
                    tags=tags or ["ai", "anthropic"],
                    published_at=_parse_date_text(date_text),
                )
            )

    return items


async def fetch_google_dev_events(tags: list[str] | None = None) -> list[ContentItem]:
    """Scrape upcoming events from developers.google.com/events (server-rendered)."""
    url = "https://developers.google.com/events"
    try:
        html = await _fetch_html(url)
    except Exception:
        logger.exception("Failed to fetch Google Developer events")
        return []

    tree = HTMLParser(html)
    items = []

    # Google uses devsite-landing-row-item cards for upcoming events
    for card in tree.css(".devsite-landing-row-item"):
        title_node = card.css_first("h3") or card.css_first("h4")
        link_node = card.css_first("a[href]")

        title = title_node.text(strip=True) if title_node else ""
        if not title:
            continue

        href = link_node.attributes.get("href", "") if link_node else ""
        if href and not href.startswith("http"):
            href = "https://developers.google.com" + href
        event_url = href or url

        # Extract date and location from card text (format: "TitleMarch 5-6 (NYC) | In-person...")
        card_text = card.text(strip=True)
        published = None
        location = ""
        # Strip the title prefix to get the metadata text
        meta_text = card_text[len(title) :] if card_text.startswith(title) else card_text
        # Look for date patterns like "March 4", "May 19-20"
        date_match = re.search(
            r"((?:January|February|March|April|May|June|July|August|September"
            r"|October|November|December)\s+\d{1,2})",
            meta_text,
        )
        if date_match:
            published = _parse_date_text(date_match.group(1))
        # Extract location from parentheses, e.g. "(Berlin)"
        loc_match = re.search(r"\(([^)]+)\)", meta_text)
        if loc_match:
            location = loc_match.group(1)
        # Build a clean summary
        fmt_match = re.search(r"\|\s*(Online|In-person|Virtual)", meta_text)
        summary_parts = []
        if date_match:
            summary_parts.append(date_match.group(1))
        if location:
            summary_parts.append(location)
        if fmt_match:
            summary_parts.append(fmt_match.group(1))
        clean_summary = " | ".join(summary_parts) if summary_parts else ""

        items.append(
            ContentItem(
                id=make_id(event_url),
                url=event_url,
                title=title,
                summary=clean_summary,
                source_name="Google Developer Events",
                source_type="events",
                tags=tags or ["ai", "google"],
                published_at=published,
            )
        )

    return items


async def run_events_ingestion(backend, sources_config: dict) -> int:
    """Fetch all configured event sources and store new items."""
    sources = sources_config.get("sources", {})
    event_sources = sources.get("events", [])
    if not event_sources:
        return 0

    total_new = 0

    for src in event_sources:
        name = src.get("name", "")
        scraper = src.get("scraper", "")
        tags = src.get("tags", [])

        try:
            if scraper == "anthropic":
                items = await fetch_anthropic_events(tags=tags)
            elif scraper == "google_dev":
                items = await fetch_google_dev_events(tags=tags)
            else:
                logger.warning(f"Unknown event scraper: {scraper}")
                continue

            source_key = name or f"events:{scraper}"
            new_count = backend.ingest_items(source_key, items)
            if new_count > 0:
                logger.info(f"Fetched {new_count} new events from {source_key}")
            total_new += new_count
        except Exception:
            logger.exception(f"Failed to fetch events from {name}")

    return total_new
