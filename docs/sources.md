# Source Configuration Guide

All sources are defined in `config/sources.yml`.

## Source Types

### RSS (direct feeds)
No intermediary needed — fetched directly via feedparser.

```yaml
rss:
  - url: "https://openai.com/news/rss.xml"
    name: "OpenAI Blog"
    tags: [ai, openai, company]
```

**Tips:**
- Some sites block requests without a User-Agent (e.g. OpenAI). The fetcher includes a browser-like User-Agent header.
- Tags are applied to all items from this source (source-level, not per-item).

### YouTube (native RSS)
YouTube provides RSS feeds per channel. No RSSHub needed.

```yaml
youtube:
  - channel_id: "UCYO_jab_esuFRV4b17AJtAw"
    name: "Andrej Karpathy"
    tags: [ai, research, deep-learning]
```

Find a channel ID: go to the channel page → View Source → search for `channelId` or `externalId`.

**Note:** YouTube Shorts appear as separate feed entries. If a Short has the same title as a full video from the same channel, it's automatically marked as a duplicate and hidden from the dashboard.

### Twitter
Uses Chrome cookies (via rookiepy) to call Twitter's GraphQL API. No API keys needed — just stay logged into x.com in Chrome.

```yaml
twitter:
  - handle: "trq212"
    tags: [ai]
```

**Setup:** Run `uv run ainews twitter-setup` to verify cookies are accessible.

**How it works:**
1. rookiepy reads auth_token and ct0 from Chrome's cookie database
2. Calls `UserByScreenName` GraphQL endpoint to get user ID
3. Calls `UserTweets` endpoint to get recent tweets
4. Tweet text becomes both `title` (truncated to 100 chars) and `summary`

### RSSHub (scraped sites)
For sites without native RSS. Requires a self-hosted RSSHub instance (Docker).

```yaml
rsshub:
  - route: "/anthropic/news"
    name: "Anthropic News"
    display_type: "rss"
    tags: [ai, anthropic, company]
```

The route is appended to `rsshub_base` (default: `http://localhost:1200`).

**Start RSSHub:** `docker compose -f docker/docker-compose.yml up -d`

**Finding routes:** Check [RSSHub docs](https://docs.rsshub.app/) for available routes. Not all routes work — test with `curl http://localhost:1200/<route>` before adding.

### Xiaohongshu (via RSSHub)
Xiaohongshu sources use RSSHub routes. Add them under the `rsshub` section with `display_type: xiaohongshu`.

```yaml
rsshub:
  - route: "/xiaohongshu/user/62fb991800000000120027ee/notes"
    name: "XHS User"
    display_type: "xiaohongshu"
    tags: [ai]
```

**Setup:** Use `image: diygod/rsshub:chromium-bundled` in `docker/docker-compose.yml` (the default). The route format is `/xiaohongshu/user/{user_id}/notes`. Find the user_id from the XHS profile URL: `xiaohongshu.com/user/profile/{user_id}`.

### Luma Events
Events from lu.ma, routed through RSSHub.

```yaml
luma:
  - handle: "dtc-events"
    tags: [events, ai, copenhagen]
```

**Note:** For Luma items, `published_at` is the event date (not when fetched). The dashboard shows "Event: Mar 24, 2026" to distinguish this. Events are sorted by `fetched_at` so future events don't float to the top.

### ArXiv Keyword Queries
Uses the arXiv API to search for papers matching specific queries.

```yaml
arxiv_queries:
  - query: "cat:cs.AI+AND+abs:transformer"
    name: "arXiv: transformers"
    tags: [ai, research, transformers]
```

**Query syntax:** See [arXiv API docs](https://info.arxiv.org/help/api/user-manual.html). Common fields: `cat:` (category), `abs:` (abstract), `ti:` (title), `au:` (author).

### Event Scrapers
HTML scrapers for tech company event pages.

```yaml
events:
  - scraper: "anthropic"
    name: "Anthropic Events"
    tags: [ai, anthropic]
  - scraper: "google_dev"
    name: "Google Developer Events"
    tags: [ai, google]
```

Available scrapers: `anthropic` (Webflow CMS), `google_dev` (developers.google.com/events).

### GitHub Trending
Scrapes top trending repos from trendshift.io daily, plus all-time most-featured repos.

```yaml
github_trending:
    tags: [github, trending, open-source]
```

This is a single config entry (not a list). Two tabs on the Trends page:
- **Daily Trending** — top 25 repos by daily engagement score
- **Trending History** — top 25 all-time most-featured repos on GitHub Trending

### Leaderboard & Event Links
Reference links for manual browsing — not ingested by the pipeline.

```yaml
leaderboard:
  - url: "https://arena.ai/leaderboard"
    name: "Arena (Chatbot Arena)"
    tags: [ai, benchmarks, evals]

event_links:
  - url: "https://www.anthropic.com/events"
    name: "Anthropic Events"
    tags: [ai, anthropic, events]
```

## Adding a New Source

1. Determine the source type (RSS, YouTube, Twitter, RSSHub, Luma, ArXiv, Events, GitHub Trending)
2. Add an entry to the appropriate section in `config/sources.yml`
3. Choose meaningful tags — these are displayed on the dashboard and used for filtering
4. Test: run `uv run ainews fetch` and check the dashboard

## Current Sources

| Type | Count | Examples |
|------|-------|---------|
| RSS | 15 feeds | arXiv, OpenAI, DeepMind, Meta, Apple, Microsoft, NVIDIA, HuggingFace, Claude Code |
| YouTube | 5 channels | Karpathy, Nate Herk, TechWorld with Nana, Stanford, AI Engineer |
| Twitter | 4 handles | @trq212, @karpathy, @bcherny, @simonw |
| RSSHub | 4 routes | Anthropic News, Cohere Blog, Anthropic Research, XHS |
| Luma | 2 handles | dtc-events, claudecommunity |
| ArXiv queries | 3 queries | transformers, LLMs, RL |
| Events | 2 scrapers | Anthropic Events, Google Developer Events |
| GitHub Trending | 1 source | trendshift.io (daily + history) |

## Known Limitations

- **Mistral AI** has no RSS feed and no working RSSHub route
- **XHS** requires the chromium-bundled RSSHub image (captcha issues may occur)
- **Tags are source-level** — every item from a source gets the same tags, not per-item content tags
- **RSS has no "since" support** — full feed is re-downloaded every cycle, but only new items are stored

---

*Last updated: 2026-03-16*
