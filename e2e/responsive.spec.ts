import { test, expect } from "@playwright/test";

// All static pages to test across every viewport
const pages = [
  { name: "feeds", path: "/" },
  { name: "leaderboard", path: "/leaderboard" },
  { name: "events", path: "/events" },
  { name: "trends", path: "/trends" },
  { name: "about", path: "/about" },
];

// Disable animations and wait for Tailwind CSS to load
async function stabilizePage(page: import("@playwright/test").Page) {
  // Wait for Tailwind browser runtime to finish rendering
  await page.waitForLoadState("networkidle");

  // Inject CSS to disable animations/transitions for stable screenshots
  await page.addStyleTag({
    content: `
      *, *::before, *::after {
        animation-duration: 0s !important;
        animation-delay: 0s !important;
        transition-duration: 0s !important;
        transition-delay: 0s !important;
      }
    `,
  });

  // Small wait for Tailwind to process styles
  await page.waitForTimeout(500);
}

for (const pg of pages) {
  test(`${pg.name} page renders correctly`, async ({ page }) => {
    await page.goto(pg.path);
    await stabilizePage(page);
    await expect(page).toHaveScreenshot(`${pg.name}.png`, {
      fullPage: true,
    });
  });
}

// Specific responsive behavior tests
test("hamburger menu works on mobile", async ({ page, isMobile, viewport }) => {
  // Hamburger only shows below Tailwind's sm breakpoint (640px)
  const isNarrow = viewport ? viewport.width < 640 : isMobile;
  test.skip(!isNarrow, "Only relevant for viewports below 640px");
  await page.goto("/");
  await stabilizePage(page);

  // Hamburger button should be visible on mobile
  const hamburger = page.locator("#hamburger-btn");
  await expect(hamburger).toBeVisible();

  // Desktop nav links should be hidden
  const mobileLinks = page.locator("#nav-links-mobile");
  await expect(mobileLinks).toBeHidden();

  // Click hamburger to open mobile menu
  await hamburger.click();
  await expect(mobileLinks).toBeVisible();

  // Mobile menu links should have adequate touch targets (py-2 = 8px + text = ~36px+)
  const feedsLink = mobileLinks.locator("a", { hasText: "Feeds" }).first();
  await expect(feedsLink).toBeVisible();

  // Verify no horizontal overflow
  const hasOverflow = await page.evaluate(() => {
    return document.documentElement.scrollWidth > document.documentElement.clientWidth;
  });
  expect(hasOverflow, "Navigation causes horizontal scroll").toBe(false);
});

test("navigation links visible on desktop", async ({ page, isMobile }) => {
  test.skip(isMobile === true, "Only relevant for desktop viewports");
  await page.goto("/");
  await stabilizePage(page);

  // Desktop nav links should be visible
  const navLinks = page.locator("nav a, header a").first();
  await expect(navLinks).toBeVisible();
});

test("no horizontal scrollbar on any page", async ({ page }) => {
  for (const pg of pages) {
    await page.goto(pg.path);
    await stabilizePage(page);

    const hasHorizontalScroll = await page.evaluate(() => {
      return document.documentElement.scrollWidth > document.documentElement.clientWidth;
    });

    expect(
      hasHorizontalScroll,
      `${pg.name} has unwanted horizontal scroll`
    ).toBe(false);
  }
});

test("text is not truncated or overflowing", async ({ page }) => {
  await page.goto("/");
  await stabilizePage(page);

  const overflowingElements = await page.evaluate(() => {
    const elements = document.querySelectorAll("h1, h2, h3, p, a, span");
    const overflowing: string[] = [];
    elements.forEach((el) => {
      const style = window.getComputedStyle(el);
      if (
        style.textOverflow === "ellipsis" ||
        style.overflow === "hidden" ||
        style.overflowX === "hidden" ||
        style.overflowX === "auto" ||
        style.overflowX === "scroll"
      )
        return;
      const text = (el.textContent || "").trim();
      if (!text) return; // skip empty layout containers
      const rect = el.getBoundingClientRect();
      if (rect.width > 0 && el.scrollWidth > el.clientWidth + 1) {
        overflowing.push(
          `<${el.tagName}> "${text.slice(0, 50)}" (${el.scrollWidth}>${el.clientWidth})`
        );
      }
    });
    return overflowing;
  });

  if (overflowingElements.length > 0) {
    console.log("Elements with unexpected overflow:", overflowingElements);
  }
  expect(
    overflowingElements.length,
    `Found ${overflowingElements.length} elements with unexpected overflow`
  ).toBe(0);
});

test("mobile menu links have adequate touch targets", async ({
  page,
  isMobile,
  viewport,
}) => {
  const isNarrow = viewport ? viewport.width < 640 : isMobile;
  test.skip(!isNarrow, "Only relevant for viewports below 640px");
  await page.goto("/");
  await stabilizePage(page);

  await page.locator("#hamburger-btn").click();
  const mobileMenu = page.locator("#nav-links-mobile");
  await expect(mobileMenu).toBeVisible();

  const smallLinks = await mobileMenu.evaluate((menu) => {
    const links = menu.querySelectorAll("a");
    const tooSmall: string[] = [];
    links.forEach((el) => {
      const rect = el.getBoundingClientRect();
      if (rect.height > 0 && rect.height < 30) {
        const text = (el.textContent || "").trim().slice(0, 30);
        tooSmall.push(
          `"${text}" (${Math.round(rect.width)}×${Math.round(rect.height)})`
        );
      }
    });
    return tooSmall;
  });

  expect(smallLinks, "Mobile menu links too small for touch").toHaveLength(0);
});
