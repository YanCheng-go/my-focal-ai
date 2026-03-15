# Spike: Responsive Design Testing Strategy

**Date:** 2026-03-15
**Status:** Research complete
**Goal:** Evaluate tools and approaches for automated responsive testing of MyFocalAI static pages across mobile, tablet, and desktop viewports.

---

## Current State

MyFocalAI uses **Tailwind CSS v4 (browser CDN)** with a mobile-first approach. All 7 static pages and 6 Jinja templates have:
- Correct `<meta name="viewport">` tags
- Hamburger nav at `sm:` breakpoint (640px)
- `flex-wrap`, `overflow-x-auto`, `max-w-4xl` responsive patterns
- Dark mode with system auto-detect + manual toggle
- Responsive grids (`grid-cols-1 sm:grid-cols-2`)

**Minor gaps identified:** fixed text sizes (no fluid `clamp()`), modal edge-heaviness on <400px phones, table headers don't stack on mobile, pagination wrapping on very narrow screens.

---

## Recommended Approach: Playwright Visual Regression Testing

### Why Playwright?

| Tool | Pros | Cons |
|------|------|------|
| **Playwright (built-in)** | Free, built-in `toHaveScreenshot()`, device registry, CI-ready | Baseline management is manual |
| BackstopJS | Mature, config-driven, good diffing UI | Puppeteer-only, slower updates, no device registry |
| Percy (BrowserStack) | AI diffing, cloud dashboard, 5k free screenshots/month | Paid at scale, external dependency |
| Applitools Eyes | AI-powered visual AI, Figma comparison (2026) | Expensive, overkill for this project |
| Chromatic | Best for Storybook component libs | Not applicable (no Storybook) |
| Loki | Self-hosted Storybook visual testing | Not applicable |

**Verdict: Playwright** — already installed (v1.58.2), zero cost, built-in device emulation, integrates with existing CI. Perfect for a static HTML site.

### Device Matrix

| Profile | Device | Viewport | Use Case |
|---------|--------|----------|----------|
| `mobile-small` | iPhone SE | 320×568 | Smallest common phone |
| `mobile` | iPhone 15 | 393×852 | Most popular phone |
| `mobile-large` | iPhone 15 Pro Max | 430×932 | Large phone |
| `tablet` | iPad Mini | 768×1024 | Tablet portrait |
| `desktop` | Desktop Chrome | 1280×720 | Standard desktop |
| `desktop-wide` | Custom | 1920×1080 | Wide desktop |

### Pages to Test

All 7 static pages: `index.html`, `admin.html`, `leaderboard.html`, `events.html`, `trends.html`, `ccc.html`, `about.html`

---

## Setup

### Dependencies

```bash
npm init -y
npm install -D @playwright/test
npx playwright install chromium
```

Only Chromium needed — visual consistency testing, not cross-browser. Add `e2e/` directory for tests, `playwright.config.ts` for configuration.

### Project Configuration

```typescript
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  retries: 0,
  use: {
    baseURL: 'http://localhost:8000',
    screenshot: 'only-on-failure',
  },
  expect: {
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.01,
    },
  },
  projects: [
    { name: 'mobile', use: { ...devices['iPhone SE'] } },
    { name: 'mobile-large', use: { ...devices['iPhone 15 Pro Max'] } },
    { name: 'tablet', use: { ...devices['iPad Mini'] } },
    { name: 'desktop', use: { viewport: { width: 1280, height: 720 } } },
    { name: 'desktop-wide', use: { viewport: { width: 1920, height: 1080 } } },
  ],
});
```

### Test Structure

```typescript
// e2e/responsive.spec.ts
import { test, expect } from '@playwright/test';

const pages = [
  { name: 'feeds', path: '/' },
  { name: 'leaderboard', path: '/leaderboard' },
  { name: 'events', path: '/events' },
  { name: 'trends', path: '/trends' },
  { name: 'about', path: '/about' },
];

for (const pg of pages) {
  test(`${pg.name} page renders correctly`, async ({ page }) => {
    await page.goto(pg.path);
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveScreenshot(`${pg.name}.png`, { fullPage: true });
  });
}
```

### Running Tests

```bash
# First run: creates baseline screenshots
npx playwright test --update-snapshots

# Subsequent runs: compare against baselines
npx playwright test

# View visual diff report on failure
npx playwright show-report
```

---

## Modern CSS Improvements to Consider

These are optional enhancements for the minor responsive gaps:

1. **Fluid typography with `clamp()`** — replace fixed `text-sm`/`text-base` with fluid sizes:
   ```css
   font-size: clamp(0.875rem, 0.8rem + 0.25vw, 1rem);
   ```

2. **Container queries (`@container`)** — make card components adapt to their container width rather than viewport. Supported in all modern browsers since 2023.

3. **Dynamic viewport units (`dvh`)** — use `100dvh` instead of `100vh` for mobile browsers where the address bar changes height.

4. **CSS `subgrid`** — align nested grid items to parent grid tracks. Full browser support since 2023.

---

## CI Integration

Add to GitHub Actions workflow:

```yaml
- name: Visual regression tests
  run: |
    npx playwright install chromium --with-deps
    uv run ainews serve &
    sleep 3
    npx playwright test
```

Baselines committed to repo in `e2e/responsive.spec.ts-snapshots/`.

---

## Decision

Use **Playwright's built-in visual regression** with 6 viewport profiles across 5 pages. No additional packages needed beyond `@playwright/test`. Run as part of CI to catch responsive regressions.

---

*Last updated: 2026-03-15*
