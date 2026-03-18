# Spike: New Item Indicator UX Patterns

**Date:** 2026-03-15
**Status:** Complete
**Backlog item:** N/A (enhancement to existing feature)
**Decision:** Keep time-based blue background highlight as primary pattern, but add a secondary "New" text label for accessibility (WCAG 1.4.1) and consider a "new since" divider line for orientation.

## Question

What are the established UI/UX patterns for indicating new/unread content in feeds? Is our current time-based blue background highlight the right approach, and does it need accessibility or usability improvements?

## Context

We implemented a "new item" indicator system in the static site (index.html, trends.html, ccc.html) that:

1. Stores a per-page `ainews_last_seen_<page>` timestamp in localStorage
2. On each visit, highlights items published after the last-seen cutoff with a blue background (`bg-blue-50/70 dark:bg-blue-950/20`)
3. Updates the timestamp on page load so highlights disappear on next visit
4. Shows red badge counts in the nav bar for pages with new items

The implementation lives in `static/badges.js` (badge counts + `isNewItem()` function) and is consumed in the render functions of `static/index.html`, `static/trends.html`, and `static/ccc.html`. The local-mode server-rendered templates (`templates/dashboard.html`) do not have this feature.

This spike investigates whether the pattern is sound and what improvements to consider.

## How Other Apps Handle New/Unread Content

### Pattern Survey

| App / Category | Indicator Type | Persistence Model | Notes |
|---|---|---|---|
| **Gmail / Email clients** | Bold text + unread count | Per-item (explicit mark-as-read) | Users manually mark read or read by opening |
| **Slack** | Bold channel name + red dot/badge + red divider line in history | Per-item (auto-mark on scroll) | Famous "red line" separator between old and new messages |
| **Feedly / Inoreader** | Unread count per feed + filtered "unread only" view | Per-item (mark-as-read on scroll or click) | Red color on feeds with unread items (Inoreader) |
| **Hacker News** | None | None | No read tracking at all -- pure chronological list |
| **Twitter/X** | "Show N new posts" banner at top | Time-based (new posts since last scroll position) | Does not highlight individual items |
| **Reddit** | Blue dot next to new comments (on revisit) | Time-based (since last visit to thread) | Requires Reddit Gold/Premium |
| **Apple News** | Algorithmically ranked, no explicit "new" markers | None visible | Relies on feed freshness, not read tracking |
| **Google News** | No per-item indicators | None visible | Sections refresh with new content |

### Key Insight

There is a clear spectrum from "no tracking" (HN, Google News) to "full per-item tracking" (Gmail, Feedly). The right choice depends on the user's relationship with the content:

- **Must-read content** (email, DMs) --> per-item read tracking
- **Should-skim content** (news feeds, RSS) --> time-based or no tracking
- **Entertainment content** (social media) --> algorithmic, no explicit tracking

Our app is a "should-skim" news aggregator. Time-based tracking is the right tier.

## Indicator Patterns Compared

### Option A: Background Color Highlight (current)

**How it works:** Items published after last visit get `bg-blue-50/70` (light) / `bg-blue-950/20` (dark) background. All other items get white/neutral background.

**Pros:**
- Subtle and non-intrusive -- does not add visual clutter
- Works well at scale (50+ new items still readable, no badge explosion)
- Familiar pattern (Reddit uses similar for new comments)
- Already implemented and tested

**Cons:**
- Violates WCAG 1.4.1: color is the only visual means of conveying "new" status
- Subtle blue tint may be invisible to users with tritanopia (blue-yellow colorblindness)
- Low contrast difference may be missed on poorly calibrated monitors
- No orientation aid -- user cannot quickly see "where do new items start"

**Effort:** Already done
**Risk:** Medium (accessibility gap)

### Option B: "New" Pill Badge per Item

**How it works:** A small colored pill (e.g., `<span class="bg-blue-100 text-blue-700 px-2 py-0.5 rounded text-xs">New</span>`) appears in the metadata row alongside source type and tags.

**Pros:**
- Accessible -- text label conveys meaning without relying on color
- Consistent with existing tag/badge visual language (indigo pills already used for tags, tiers)
- Scannable -- eye can quickly spot "New" labels while scrolling
- Works for screen readers

**Cons:**
- Adds visual noise, especially when 50+ items are all "new" (after a long absence)
- When everything is "new," nothing feels new (badge fatigue / "red dot blindness")
- More DOM elements per item

**Effort:** XS (add one conditional span in the render function)
**Risk:** Low

### Option C: Divider Line ("New since your last visit")

**How it works:** A horizontal rule or labeled separator inserted between the last "new" item and the first "old" item, similar to Slack's red line or the "new comments below" pattern.

**Pros:**
- Provides clear spatial orientation ("everything above this line is new")
- Single element regardless of how many new items exist -- no per-item noise
- Familiar from Slack, email threading, forum software
- Accessible -- text label readable by screen readers

**Cons:**
- Only works in chronological sort order (breaks with "by score" sorting)
- Awkward when all items are new (divider at the very bottom) or none are new (no divider)
- Pagination complicates placement -- divider might be on page 2
- Does not help when scanning mid-page; only useful at the boundary

**Effort:** S (insert a conditional element between items during render)
**Risk:** Low

### Option D: Dot Indicator (Blue Dot)

**How it works:** A small colored dot (6-8px circle) appears to the left of each new item's title, similar to iOS notification dots.

**Pros:**
- Compact -- minimal visual footprint per item
- Familiar from iOS, macOS notification patterns
- Scales well (dots are small enough that 50 of them do not overwhelm)

**Cons:**
- Still color-only (same WCAG 1.4.1 concern as background highlight)
- Small target makes it easy to miss, especially on mobile
- Conflicts with existing left border color (source type indicator)
- Dot without text label is ambiguous -- what does the dot mean?

**Effort:** XS
**Risk:** Medium (accessibility, ambiguity)

### Option E: Bold Text / Font Weight Change

**How it works:** New item titles are rendered with `font-bold` or `font-extrabold`; old items use `font-semibold` (current default).

**Pros:**
- Does not rely on color -- accessible to colorblind users
- Familiar from email clients (unread = bold)
- Zero additional DOM elements

**Cons:**
- Current titles are already `font-semibold` so the difference to `font-bold` is subtle
- Works best in text-heavy lists (email) but less effective in card-based layouts
- When all items are new, everything is bold and the signal is lost
- Users may not consciously register the weight difference

**Effort:** XS
**Risk:** Low but low impact

## Persistence Model: Time-Based vs. Per-Item

### Time-Based Reset (current approach)

- Last-seen timestamp stored in localStorage per page
- All items newer than timestamp are "new" on arrival
- Timestamp updates on page load --> all items become "old" on refresh
- No server-side state required

**Verdict:** Appropriate for our use case. News aggregators are not inbox-zero tools. Users visit, scan what is new, and leave. They do not need to track which specific items they have read. This matches the pattern used by Twitter ("N new posts"), Reddit (new comments since last visit), and the "river of news" philosophy championed by Dave Winer.

### Per-Item Read Tracking

- Each item gets a read/unread boolean flag
- Flag flips when user clicks, scrolls past, or explicitly marks
- Requires persistent storage (localStorage for local, database for cross-device)
- Enables "unread only" filtering

**Verdict:** Overkill for our project. Adds significant complexity (storage, sync, UI for mark-as-read) for marginal benefit. RSS readers (Feedly, Inoreader) use this because their users subscribe to specific feeds and want inbox-zero behavior. Our users browse a curated aggregation -- different mental model.

### Hybrid: Time-Based with Manual "Mark All Read"

- Same as time-based, but add a button: "Mark all as read" (resets timestamp to now)
- User can dismiss highlights without refreshing the page

**Verdict:** Nice-to-have but not urgent. The current "refresh to dismiss" behavior is intuitive enough.

## Accessibility Analysis

### Current Violation

The blue background highlight violates [WCAG 2.1 Success Criterion 1.4.1: Use of Color](https://www.w3.org/WAI/WCAG21/Understanding/use-of-color.html):

> "Color is not used as the only visual means of conveying information, indicating an action, prompting a response, or distinguishing a visual element."

The blue background is the **only** visual cue that an item is new. A colorblind user or a user with a monochrome display would see no difference.

### How to Fix

Per WCAG and the [NNGroup research on visual indicators](https://www.nngroup.com/articles/visual-indicators-differentiators/), the most effective approach combines **color + a secondary non-color indicator**. Specifically:

1. **Keep the background highlight** (works well for sighted users with normal color vision)
2. **Add a text label** (a "New" pill badge) as a redundant indicator
3. Optionally add the divider line for spatial orientation

The NNGroup study found that combining color with icons/text made users **37% faster** at finding target items compared to text alone. Multi-dimensional cues consistently outperformed single-dimension cues.

### Color Contrast Check

The current highlight colors:
- Light mode: `bg-blue-50/70` (#eff6ff at 70% opacity) on white -- very low contrast difference
- Dark mode: `bg-blue-950/20` (#172554 at 20% opacity) on neutral-950 -- very low contrast difference

These are intentionally subtle, which is good for avoiding visual noise but bad for discoverability. The text label compensates for this.

## Recommendation

**Adopt a layered approach (Option A + B + C):**

1. **Keep the blue background highlight** -- it provides a pleasant ambient signal for most users without adding clutter. No changes needed.

2. **Add a "New" pill badge** in the metadata row of each new item. Use the existing tag/badge visual style for consistency:
   ```html
   <span class="bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-400 px-2 py-0.5 rounded text-xs font-medium">New</span>
   ```
   This fixes the WCAG 1.4.1 violation and makes the indicator scannable.

3. **Consider adding a divider line** between new and old items on the first page (when in date sort order). This is lower priority but provides helpful orientation:
   ```html
   <div class="flex items-center gap-3 my-4 text-xs text-gray-400">
     <div class="flex-1 border-t border-gray-200 dark:border-neutral-700"></div>
     <span>New items above</span>
     <div class="flex-1 border-t border-gray-200 dark:border-neutral-700"></div>
   </div>
   ```

4. **Keep time-based persistence** -- do not add per-item read tracking. The current model fits the "news river" mental model.

5. **No changes to nav badge counts** -- the red badges already work well and follow Material Design badge conventions (small, numeric, positioned on navigation elements).

## Implementation Notes

The changes are contained to the `render()` / item-template code in three files:
- `static/index.html` (line 315-316, the `isNew` / `bgCls` logic)
- `static/trends.html` (line 62-63)
- `static/ccc.html` (line 47-48)

The "New" badge is a single conditional span added to the metadata row. The divider line is a conditional element inserted in the render loop when transitioning from new to old items. Both changes are XS effort.

The server-rendered templates (`templates/dashboard.html`) do not have `isNewItem()` and would need separate implementation if desired (via a cookie or session-based last-seen timestamp).

## Next Steps

- [ ] Add "New" pill badge to item metadata row in `static/index.html`, `static/trends.html`, `static/ccc.html` (fixes WCAG 1.4.1)
- [ ] Consider adding a "new items above" divider line between new and old items (optional, lower priority)
- [ ] Verify highlight colors work in both light and dark mode with browser accessibility tools
- [ ] Decide whether to implement new-item indicators in the server-rendered localhost templates (currently only static site has this feature)

## References

- [WCAG 2.1 SC 1.4.1: Use of Color](https://www.w3.org/WAI/WCAG21/Understanding/use-of-color.html) -- color must not be the only visual means of conveying information
- [NNGroup: Visual Indicators to Differentiate Items in a List](https://www.nngroup.com/articles/visual-indicators-differentiators/) -- combining color + icon makes users 37% faster at finding items
- [NNGroup: Indicators, Validations, and Notifications](https://www.nngroup.com/articles/indicators-validations-notifications/) -- indicators should be contextual, conditional, and passive
- [Red Dot Blindness: A Human-First Approach to Badging (Braze)](https://www.braze.com/resources/articles/beware-red-dot-badging) -- overuse of badge indicators causes users to ignore them
- [Badge UI Design: Best Practices (Mobbin)](https://mobbin.com/glossary/badge) -- badges should be non-interactive, compact, and not overused
- [Material Design 3: Badges](https://m3.material.io/components/badges/guidelines) -- badges show counts or status on navigation items
- [Section508.gov: Making Color Usage Accessible](https://www.section508.gov/create/making-color-usage-accessible/) -- include text labels alongside color-based indicators
- [The News Feed (UX Magazine)](https://uxmag.com/articles/the-news-feed) -- discussion of feed design patterns and user engagement
- [Current RSS Reader (TechCrunch)](https://techcrunch.com/2026/02/19/current-is-a-new-rss-reader-thats-more-like-a-river-than-an-inbox/) -- "river of news" approach to avoid inbox anxiety
- [Feedly: Show Read and Unread Articles](https://docs.feedly.com/article/264-how-to-show-both-read-and-unread-articles) -- per-item read tracking in RSS readers
- [Slack: View Unread Messages](https://slack.com/help/articles/226410907-View-all-your-unread-messages) -- divider line and bold channel patterns

*Last updated: 2026-03-15*
