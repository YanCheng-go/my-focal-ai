import { test, expect } from "@playwright/test";

// Reuse the same page-stabilization helper from responsive.spec.ts
async function stabilizePage(page: import("@playwright/test").Page) {
  await page.waitForLoadState("networkidle");
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
  await page.waitForTimeout(500);
}

test.describe("Trends page tabs", () => {
  test("all 3 main tabs are visible on GitHub tab", async ({ page }) => {
    await page.goto("/trends?tab=daily");
    await stabilizePage(page);

    const tabBar = page.locator("#tab-bar");
    await expect(tabBar.locator("a", { hasText: "GitHub" })).toBeVisible();
    await expect(tabBar.locator("a", { hasText: "AI Tools" })).toBeVisible();
    await expect(
      tabBar.locator("a", { hasText: "Agent Skills" })
    ).toBeVisible();
  });

  test("GitHub tab shows correct subtitle", async ({ page }) => {
    await page.goto("/trends?tab=daily");
    await stabilizePage(page);

    const subtitle = page.locator("p.text-sm.text-gray-500").first();
    await expect(subtitle).toContainText("GitHub Trending");
    await expect(subtitle).toContainText("trendshift.io");
  });

  test("AI Tools tab shows correct subtitle", async ({ page }) => {
    await page.goto("/trends?tab=claude");
    await stabilizePage(page);

    const subtitle = page.locator("p.text-sm.text-gray-500").first();
    await expect(subtitle).toContainText("AI Tools");
    await expect(subtitle).toContainText("aitmpl.com");
  });

  test("Agent Skills tab shows correct subtitle", async ({ page }) => {
    await page.goto("/trends?tab=skillssh");
    await stabilizePage(page);

    const subtitle = page.locator("p.text-sm.text-gray-500").first();
    await expect(subtitle).toContainText("Agent Skills");
    await expect(subtitle).toContainText("skills.sh");
  });

  test("GitHub tab has Daily and History sub-tabs", async ({ page }) => {
    await page.goto("/trends?tab=daily");
    await stabilizePage(page);

    const subtabs = page.locator("#github-subtabs a");
    await expect(subtabs).toHaveCount(2);
    await expect(subtabs.nth(0)).toHaveText("Daily");
    await expect(subtabs.nth(1)).toHaveText("History");
  });

  test("GitHub Daily sub-tab is active by default", async ({ page }) => {
    await page.goto("/trends?tab=daily");
    await stabilizePage(page);

    const dailyBtn = page
      .locator("#github-subtabs a", { hasText: "Daily" })
      .first();
    const historyBtn = page.locator("#github-subtabs a", {
      hasText: "History",
    });

    await expect(dailyBtn).toHaveClass(/bg-blue-100/);
    await expect(historyBtn).toHaveClass(/bg-white/);
  });

  test("AI Tools sub-tabs contain all expected types", async ({ page }) => {
    await page.goto("/trends?tab=claude");
    await stabilizePage(page);

    const subtabs = page.locator("#claude-subtabs a");
    const expectedLabels = [
      "All",
      "Skills",
      "Agents",
      "Commands",
      "Settings",
      "Hooks",
      "MCPs",
    ];
    await expect(subtabs).toHaveCount(expectedLabels.length);
    for (let i = 0; i < expectedLabels.length; i++) {
      await expect(subtabs.nth(i)).toHaveText(expectedLabels[i]);
    }
  });

  test("Agent Skills sub-tabs contain all expected types", async ({
    page,
  }) => {
    await page.goto("/trends?tab=skillssh");
    await stabilizePage(page);

    const subtabs = page.locator("#skillssh-subtabs a");
    const expectedLabels = ["All Time", "Trending (24h)", "Hot", "Official"];
    await expect(subtabs).toHaveCount(expectedLabels.length);
    for (let i = 0; i < expectedLabels.length; i++) {
      await expect(subtabs.nth(i)).toHaveText(expectedLabels[i]);
    }
  });

  test("AI Tools table headers render correctly", async ({ page }) => {
    await page.goto("/trends?tab=claude");
    await stabilizePage(page);

    const header = page.locator(".grid.uppercase").first();
    await expect(header).toContainText("#");
    await expect(header).toContainText("Component");
    await expect(header).toContainText("Today");
    await expect(header).toContainText("Week");
    await expect(header).toContainText("Month");
    await expect(header).toContainText("Total");
  });

  test("Agent Skills table headers render correctly", async ({ page }) => {
    await page.goto("/trends?tab=skillssh");
    await stabilizePage(page);

    const header = page.locator(".grid.uppercase").first();
    await expect(header).toContainText("#");
    await expect(header).toContainText("GEN");
    await expect(header).toContainText("SOCKET");
    await expect(header).toContainText("SNYK");
    await expect(header).toContainText("Installs");
  });
});
