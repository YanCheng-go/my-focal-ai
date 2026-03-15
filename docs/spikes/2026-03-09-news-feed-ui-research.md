# Spike: News Feed UI/UX Redesign Research

**Date:** 2026-03-09
**Status:** Complete
**Backlog item:** #69
**Decision:** Adopt a Hacker News-inspired dense list layout with Tailwind CSS (CDN for prototyping, build for production), class-based dark/light theme toggle, and Inter + system font stack.

## Question

What UI/UX patterns, styling framework, and visual direction should guide the redesign of the MyFocalAI dashboard?

## Context

The current site uses hand-written inline `<style>` blocks duplicated across 7 templates and 6 static HTML files. Every page re-declares the same base styles (body, container, nav, items, tags, pagination) with minor variations. The site is dark-only with no theme toggle. There is no shared CSS file, no utility framework, and no design tokens. Adding new pages or changing the visual language requires editing 13+ files. Issue #69 tracks the UI redesign, and issue #66 tracks notification badges.

## 1. News Feed Layout Patterns Analyzed

### Hacker News / Lobsters (Minimalist Text List)

- **Layout:** Single-column ranked list, no cards, no images. Each item is one or two lines: title, domain, metadata row (points, author, time, comments).
- **Density:** Extremely high -- 30+ items visible without scrolling on desktop.
- **Typography:** Small monospaced or system font, minimal hierarchy. HN uses Verdana 10pt; Lobsters uses system sans-serif.
- **Color:** Near-zero color. HN uses orange for the header and gray for metadata. Lobsters uses tag colors as the only accent.
- **Filtering:** HN has none. Lobsters uses a tag-based filtering system with colored tag pills -- closest to the current MyFocalAI approach.
- **Relevance to this project:** HIGH. The current site already follows this pattern. The data density is appropriate for a power-user tool. Tags and scores are the main visual differentiators.

### TechCrunch / The Verge / Ars Technica (Media-Rich Cards)

- **Layout:** Multi-column grid of cards with hero images, headlines, excerpts.
- **Density:** Low -- 4-8 items visible per viewport. Heavy use of whitespace.
- **Typography:** Large headlines (1.5-2rem), body in serif or sans-serif, strong hierarchy.
- **Color:** Brand-heavy accent colors. The Verge uses bold geometric shapes; Ars uses a dark sidebar.
- **Filtering:** Category-based navigation (top nav or sidebar), no inline filters.
- **Relevance:** LOW. This project aggregates text-heavy items without images. Cards with thumbnails would be empty for RSS/Twitter content.

### Feedly / Inoreader (RSS Reader)

- **Layout:** Three-pane (sidebar sources, list, detail) or condensed list. Feedly offers Magazine, Cards, and Title-only views. Title-only is most relevant.
- **Density:** Configurable. Title-only view is comparable to HN. Magazine view shows excerpts.
- **Typography:** Inter or system fonts, 14-16px body, clear hierarchy between title and metadata.
- **Color:** Neutral backgrounds, green/blue accent for read state, subtle source-type icons.
- **Filtering:** Source tree in sidebar, saved searches, boards. Tag-based filtering similar to this project.
- **Relevance:** MEDIUM. The source-type filter bar and tag dropdown already provide Feedly-like filtering without the complexity of a three-pane layout.

### GitHub Trending / Explore

- **Layout:** Single-column list of repository cards. Each card: repo name, description, language, stars, forks, star trend.
- **Density:** Medium -- 8-12 items per viewport.
- **Typography:** System font stack (same as this project). Repo names in 16px bold, descriptions in 14px gray.
- **Color:** Minimal. Language color dots, subtle border separators. Star count in yellow.
- **Filtering:** Time range (daily/weekly/monthly), language dropdown, spoken language.
- **Relevance:** HIGH for the Trends page specifically. The current Trends page already mirrors this layout.

### Bloomberg Terminal / Financial Dashboards (Data-Dense)

- **Layout:** Multi-panel grid with real-time data tables, charts, and tickers.
- **Density:** Maximum -- every pixel carries information.
- **Typography:** Small monospaced fonts (11-12px), tabular numbers for alignment.
- **Color:** Dark background (#0a0a0a-#1a1a1a), green/red for directional data, blue for links. Muted palette overall.
- **Filtering:** Complex multi-faceted filters, keyboard shortcuts.
- **Relevance:** MEDIUM. The dark palette and data density are appropriate. The green/yellow/gray score tiers already borrow this aesthetic.

### Recommended Layout: Enhanced Dense List

Keep the current single-column list layout (Hacker News/Lobsters style) but improve it:
- Tighten vertical spacing between items (current 12px gap is good)
- Add subtle left-border color coding by source type (2-3px colored left border)
- Keep score badges right-aligned (current pattern works well)
- Add relative timestamps ("2h ago") alongside absolute dates
- Consider a compact/comfortable density toggle (stored in localStorage)

## 2. Dark + Light Theme Implementation

### Recommended Approach: CSS Custom Properties + Tailwind `dark:` Variant

**Step 1: Define custom variant (Tailwind v4 syntax)**

```css
/* In a <style type="text/tailwindcss"> block or app.css */
@import "tailwindcss";
@custom-variant dark (&:where(.dark, .dark *));
```

**Step 2: Theme toggle script (place in `<head>` to prevent FOUC)**

```html
<script>
  document.documentElement.classList.toggle(
    "dark",
    localStorage.theme === "dark" ||
      (!("theme" in localStorage) &&
        window.matchMedia("(prefers-color-scheme: dark)").matches)
  );
</script>
```

**Step 3: Toggle button handler**

```javascript
function toggleTheme() {
  const isDark = document.documentElement.classList.toggle("dark");
  localStorage.theme = isDark ? "dark" : "light";
}

// Reset to system preference
function useSystemTheme() {
  localStorage.removeItem("theme");
  document.documentElement.classList.toggle(
    "dark",
    window.matchMedia("(prefers-color-scheme: dark)").matches
  );
}
```

**Step 4: Three-state toggle UI (Light / System / Dark)**

```html
<div class="flex items-center gap-1 text-sm">
  <button onclick="setTheme('light')" class="px-2 py-1 rounded">Light</button>
  <button onclick="setTheme('system')" class="px-2 py-1 rounded">System</button>
  <button onclick="setTheme('dark')" class="px-2 py-1 rounded">Dark</button>
</div>
```

### Color Palette Recommendation

**Dark theme (default, matching current site):**

| Token             | Value     | Usage                              |
|-------------------|-----------|------------------------------------|
| `--bg-primary`    | `#0a0a0a` | Page background                    |
| `--bg-surface`    | `#111111` | Card/item background               |
| `--bg-elevated`   | `#1a1a1a` | Inputs, dropdowns, hover states    |
| `--border`        | `#222222` | Default borders                    |
| `--border-hover`  | `#333333` | Hover borders                      |
| `--text-primary`  | `#e0e0e0` | Titles, body text                  |
| `--text-secondary`| `#999999` | Summaries, descriptions            |
| `--text-muted`    | `#666666` | Metadata, timestamps               |
| `--accent`        | `#7cb8ff` | Links, active states               |
| `--accent-hover`  | `#a3d0ff` | Link hover                         |
| `--score-high-bg` | `#1a3d1a` | Score >= 0.7                       |
| `--score-high-fg` | `#4ade80` |                                    |
| `--score-mid-bg`  | `#3d3d1a` | Score 0.4-0.7                      |
| `--score-mid-fg`  | `#facc15` |                                    |
| `--tag-bg`        | `#1a1a2e` | Tag pills                          |
| `--tag-fg`        | `#818cf8` |                                    |

**Light theme:**

| Token             | Value     | Usage                              |
|-------------------|-----------|------------------------------------|
| `--bg-primary`    | `#fafafa` | Page background                    |
| `--bg-surface`    | `#ffffff` | Card/item background               |
| `--bg-elevated`   | `#f0f0f0` | Inputs, dropdowns                  |
| `--border`        | `#e0e0e0` | Default borders                    |
| `--border-hover`  | `#cccccc` | Hover borders                      |
| `--text-primary`  | `#1a1a1a` | Titles, body text                  |
| `--text-secondary`| `#555555` | Summaries                          |
| `--text-muted`    | `#888888` | Metadata                           |
| `--accent`        | `#1d5a9e` | Links                              |
| `--accent-hover`  | `#144072` | Link hover                         |
| `--score-high-bg` | `#dcfce7` | Score >= 0.7                       |
| `--score-high-fg` | `#166534` |                                    |
| `--score-mid-bg`  | `#fef9c3` | Score 0.4-0.7                      |
| `--score-mid-fg`  | `#854d0e` |                                    |
| `--tag-bg`        | `#e8e8f4` | Tag pills                          |
| `--tag-fg`        | `#4338ca` |                                    |

These can be defined as Tailwind theme tokens:

```html
<style type="text/tailwindcss">
  @theme {
    --color-bg-primary: var(--bg-primary);
    --color-bg-surface: var(--bg-surface);
    --color-bg-elevated: var(--bg-elevated);
    --color-border: var(--border);
    --color-text-primary: var(--text-primary);
    --color-text-muted: var(--text-muted);
    --color-accent: var(--accent);
  }
</style>
```

## 3. Tailwind CSS Strategy

### CDN vs Build

| Factor               | Play CDN                          | CLI/Vite Build                   |
|----------------------|-----------------------------------|----------------------------------|
| Setup effort         | One `<script>` tag                | Requires Node.js + config        |
| File size            | ~300KB JS runtime                 | ~5-15KB purged CSS               |
| Custom config        | `@theme` in `<style>` block       | Full `tailwind.config.js`        |
| `@apply` support     | Yes (via `text/tailwindcss`)      | Yes                              |
| Production-ready     | No (official docs say dev only)   | Yes                              |
| Fits this project    | Yes for now (personal tool)       | Better long-term                 |

**Recommendation:** Start with the Play CDN for rapid prototyping. The project is a personal tool with low traffic, so CDN overhead is acceptable. Migrate to a build step later if performance matters.

```html
<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
```

### Key Utility Patterns for the Feed

```html
<!-- Item card -->
<div class="bg-bg-surface border border-border rounded-lg p-4 mb-3
            hover:border-border-hover transition-colors">
  <div class="flex justify-between items-start gap-3">
    <a href="#" class="text-text-primary font-semibold hover:text-accent
                       text-[0.95rem] leading-snug">
      Title here
    </a>
    <span class="shrink-0 text-sm px-2.5 py-0.5 rounded-full font-semibold
                 bg-green-900/30 text-green-400">85</span>
  </div>
  <div class="mt-2 flex gap-2 flex-wrap text-xs text-text-muted">
    <span>Source Name</span>
    <span class="bg-tag-bg text-tag-fg px-2 py-0.5 rounded">rss</span>
    <span>2h ago</span>
  </div>
</div>

<!-- Filter bar -->
<div class="flex gap-2 flex-wrap mb-3">
  <button class="px-3 py-1.5 rounded-md text-sm border border-border
                 text-text-muted hover:border-border-hover hover:text-text-secondary
                 transition-colors">
    All
  </button>
  <button class="px-3 py-1.5 rounded-md text-sm border border-accent/50
                 bg-accent/10 text-accent">
    Twitter
  </button>
</div>

<!-- Navigation -->
<nav class="flex items-center gap-4 text-sm">
  <a href="/" class="text-accent hover:text-accent-hover">Dashboard</a>
  <a href="/trends" class="text-text-muted hover:text-text-secondary">Trends</a>
</nav>
```

### Shared Layout Pattern

Create a single base template (Jinja2) or shared `<head>` fragment to eliminate style duplication:

```html
<!-- templates/_base.html -->
<head>
  <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
  <script>/* theme toggle - inline to prevent FOUC */</script>
  <style type="text/tailwindcss">
    @custom-variant dark (&:where(.dark, .dark *));
    @theme { /* all design tokens */ }
    :root { /* light theme CSS vars */ }
    .dark { /* dark theme CSS vars */ }
  </style>
</head>
```

## 4. Notification Badge Patterns

### Implementation for "New Items Since Last Visit"

**Core concept:** Store a timestamp in localStorage when the user views a page. On next load, compare item timestamps against the stored value.

```javascript
const STORAGE_KEY = "ainews_last_seen";

function getNewItemCount(items) {
  const lastSeen = localStorage.getItem(STORAGE_KEY);
  if (!lastSeen) return 0;
  const ts = new Date(lastSeen).getTime();
  return items.filter(i =>
    new Date(i.published_at || i.fetched_at).getTime() > ts
  ).length;
}

function markAsSeen() {
  localStorage.setItem(STORAGE_KEY, new Date().toISOString());
}

// Call markAsSeen() when user scrolls to bottom or after 5s on page
```

**Per-page badges (for nav links):**

```javascript
// Store last-seen per page
const keys = {
  dashboard: "ainews_last_seen_dashboard",
  trends: "ainews_last_seen_trends",
  ccc: "ainews_last_seen_ccc",
  events: "ainews_last_seen_events"
};
```

### Badge Styles

```html
<!-- Dot badge (minimal) -->
<a href="/trends" class="relative text-sm text-text-muted">
  Trends
  <span class="absolute -top-1 -right-2 w-2 h-2 bg-accent rounded-full"></span>
</a>

<!-- Count badge -->
<a href="/trends" class="relative text-sm text-text-muted">
  Trends
  <span class="absolute -top-2 -right-4 min-w-[1.25rem] h-5 flex items-center
               justify-center text-[0.65rem] font-bold bg-accent text-white
               rounded-full px-1">3</span>
</a>

<!-- Pulse animation for new items -->
<span class="absolute -top-1 -right-2 flex h-2 w-2">
  <span class="animate-ping absolute inline-flex h-full w-full
               rounded-full bg-accent opacity-75"></span>
  <span class="relative inline-flex rounded-full h-2 w-2 bg-accent"></span>
</span>
```

### Badge Dismissal UX

- **Auto-dismiss:** Update `lastSeen` timestamp when the user visits the page. Badge disappears on next nav render.
- **Highlight new items:** Items newer than `lastSeen` get a subtle left-border accent or background tint that fades after first view.
- **Avoid badge fatigue:** Only show badges for pages with genuinely new content (trends and CCC change daily; leaderboard rarely changes).

## 5. Recommended Style Direction

### Layout: Enhanced Dense List

- Single-column, max-width 900px (keep current), centered
- Items as minimal cards with 1px border (current pattern works)
- Add 3px left border colored by source type for scan-ability
- Score badge right-aligned (keep current pill style)
- Metadata row below title with source, type tag, time

### Source Type Color Coding (left border)

| Source Type      | Color   | Tailwind Class          |
|-----------------|---------|-------------------------|
| twitter         | #1DA1F2 | `border-l-sky-400`      |
| youtube         | #FF0000 | `border-l-red-500`      |
| rss             | #F59E0B | `border-l-amber-500`    |
| arxiv           | #B31B1B | `border-l-red-800`      |
| github_trending | #818cf8 | `border-l-indigo-400`   |
| events          | #10B981 | `border-l-emerald-500`  |
| luma            | #A855F7 | `border-l-purple-500`   |

### Typography

**Font stack (no external font loading required):**

```css
--font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans',
             Helvetica, Arial, sans-serif, 'Apple Color Emoji';
--font-mono: ui-monospace, 'SFMono-Regular', 'SF Mono', Menlo, Consolas,
             'Liberation Mono', monospace;
```

This is the same stack the project already uses, and it is the right choice:
- Zero network requests (all system fonts)
- Excellent readability on all platforms
- Matches GitHub and other developer tools

If willing to add one external font, Inter (via Google Fonts or self-hosted) is the best option for UI text -- it was designed for screens and has tabular numbers useful for scores. But the system stack is sufficient for a personal tool.

**Scale:**
- Nav links: 0.85rem (13.6px) -- keep current
- Item title: 0.95rem (15.2px) -- slightly reduce from current 1rem
- Metadata/tags: 0.75-0.8rem (12-12.8px) -- keep current
- Score badge: 0.85rem bold -- keep current

### Navigation

Replace the current inline link list with a proper nav bar:

```html
<header class="border-b border-border mb-6 pb-4">
  <div class="flex items-center justify-between">
    <div class="flex items-center gap-6">
      <h1 class="text-lg font-bold text-text-primary">AI News</h1>
      <nav class="flex items-center gap-4 text-sm">
        <a href="/" class="text-accent font-medium">Feed</a>
        <a href="/trends" class="relative text-text-muted hover:text-text-secondary">
          Trends
          <!-- badge slot -->
        </a>
        <a href="/events" class="text-text-muted hover:text-text-secondary">Events</a>
        <a href="/ccc" class="text-text-muted hover:text-text-secondary">CCC</a>
        <a href="/leaderboard" class="text-text-muted hover:text-text-secondary">Leaderboard</a>
        <a href="/about" class="text-text-muted hover:text-text-secondary">About</a>
      </nav>
    </div>
    <div class="flex items-center gap-3">
      <input type="text" placeholder="Search..."
             class="bg-bg-elevated border border-border rounded-md px-3 py-1.5
                    text-sm text-text-primary placeholder-text-muted
                    focus:border-accent focus:outline-none w-48">
      <button onclick="toggleTheme()" class="text-text-muted hover:text-text-secondary"
              title="Toggle theme">
        <!-- sun/moon icon -->
      </button>
    </div>
  </div>
</header>
```

### Component Summary

| Component       | Current                           | Proposed                                    |
|----------------|-----------------------------------|---------------------------------------------|
| CSS framework   | Inline `<style>` per page         | Tailwind v4 CDN + shared `<style>` block    |
| Theme           | Dark only                         | Dark + Light + System, persisted            |
| Nav             | Inline links with gaps            | Proper `<nav>` with active state + badges   |
| Item layout     | Card with title + score           | Same + source-type left border color        |
| Filter bar      | Pills + dropdown                  | Same pattern, Tailwind classes              |
| Pagination      | Prev/numbers/Next                 | Same, simplified with Tailwind              |
| Shared styles   | None (copy-pasted)                | Single `_base.html` template or `<head>`    |
| Badge system    | None                              | localStorage-based dot/count badges         |

## Recommendation

Adopt the **Enhanced Dense List** pattern with **Tailwind CSS v4 (Play CDN)** and **class-based dark/light theme**. This preserves the current information-dense layout that suits a technical audience while solving the three main pain points: duplicated styles, no light theme, and no new-content indicators.

The migration can be done incrementally: start with a shared base template that loads Tailwind and defines tokens, then convert pages one at a time. No new runtime dependencies are needed -- the CDN is a single `<script>` tag.

Trade-offs accepted:
- Play CDN adds ~300KB JS load, acceptable for a personal/low-traffic tool
- No build step means no tree-shaking, but simplicity outweighs optimization for this use case
- System font stack over Inter avoids an external dependency at the cost of slightly less refined typography

## Next Steps

- [ ] Create a shared Jinja2 base template (`templates/_base.html`) with Tailwind CDN, theme tokens, and nav
- [ ] Migrate the dashboard page first as a proof of concept
- [ ] Implement dark/light/system theme toggle with localStorage persistence
- [ ] Add source-type left-border color coding to item cards
- [ ] Implement notification badges on nav links (Trends, CCC) using localStorage timestamps
- [ ] Migrate remaining pages (events, trends, leaderboard, ccc, about, admin) to shared base
- [ ] Mirror changes to static site pages (`static/*.html`)
- [ ] Update issue #69 (redesign UI) with the specific implementation plan
- [ ] Update issue #66 (notification badges) to reference the localStorage pattern from this spike

## References

- [Tailwind CSS Dark Mode Docs](https://tailwindcss.com/docs/dark-mode) -- official dark mode configuration and toggle patterns
- [Tailwind CSS Play CDN](https://tailwindcss.com/docs/installation/play-cdn) -- CDN setup for Tailwind v4
- [Flowbite Dark Mode Guide](https://flowbite.com/docs/customize/dark-mode/) -- practical dark mode toggle implementation
- [EightShapes: Light & Dark Color Modes](https://medium.com/eightshapes-llc/light-dark-9f8ea42c9081) -- design system approach to dual themes
- [Accessible Dark Theme Design](https://www.fourzerothree.in/p/scalable-accessible-dark-mode) -- contrast ratios and saturation guidelines
- [Badging API Guide](https://fsjs.dev/demystifying-badging-api-enhancing-user-engagement/) -- advanced badge patterns
- [Dismissible Notifications with localStorage](https://gist.github.com/celsowhite/e7d3cb6c07a0ef888ade3090e9236150) -- localStorage dismiss pattern

*Last updated: 2026-03-09*
