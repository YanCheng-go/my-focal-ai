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
  test.beforeEach(async ({ page }) => {
    await page.goto("/trends");
    await stabilizePage(page);
  });

  test("all 3 main tabs are visible and clickable", async ({ page }) => {
    const tabBar = page.locator("#tab-bar");
    const githubBtn = tabBar.locator("button", { hasText: "GitHub" });
    const aiToolsBtn = tabBar.locator("button", { hasText: "AI Tools" });
    const agentSkillsBtn = tabBar.locator("button", {
      hasText: "Agent Skills",
    });

    await expect(githubBtn).toBeVisible();
    await expect(aiToolsBtn).toBeVisible();
    await expect(agentSkillsBtn).toBeVisible();

    // All three should be clickable (not disabled)
    await expect(githubBtn).toBeEnabled();
    await expect(aiToolsBtn).toBeEnabled();
    await expect(agentSkillsBtn).toBeEnabled();
  });

  test("clicking each main tab shows the correct subtitle text", async ({
    page,
  }) => {
    const subtitle = page.locator("#subtitle");

    // Default: GitHub tab
    await expect(subtitle).toContainText("GitHub Trending");
    await expect(subtitle).toContainText("trendshift.io");

    // Switch to AI Tools
    await page.locator("#tab-bar button", { hasText: "AI Tools" }).click();
    await expect(subtitle).toContainText("AI Tools");
    await expect(subtitle).toContainText("aitmpl.com");

    // Switch to Agent Skills
    await page
      .locator("#tab-bar button", { hasText: "Agent Skills" })
      .click();
    await expect(subtitle).toContainText("Agent Skills");
    await expect(subtitle).toContainText("skills.sh");

    // Switch back to GitHub
    await page.locator("#tab-bar button", { hasText: "GitHub" }).click();
    await expect(subtitle).toContainText("GitHub Trending");
  });

  test("sub-tabs appear and disappear when switching main tabs", async ({
    page,
  }) => {
    const githubSubs = page.locator("#github-subtabs");
    const claudeSubs = page.locator("#claude-subtabs");
    const skillsshSubs = page.locator("#skillssh-subtabs");

    // Default: GitHub sub-tabs visible, others hidden
    await expect(githubSubs).toBeVisible();
    await expect(claudeSubs).toBeHidden();
    await expect(skillsshSubs).toBeHidden();

    // Switch to AI Tools
    await page.locator("#tab-bar button", { hasText: "AI Tools" }).click();
    await expect(githubSubs).toBeHidden();
    await expect(claudeSubs).toBeVisible();
    await expect(skillsshSubs).toBeHidden();

    // Switch to Agent Skills
    await page
      .locator("#tab-bar button", { hasText: "Agent Skills" })
      .click();
    await expect(githubSubs).toBeHidden();
    await expect(claudeSubs).toBeHidden();
    await expect(skillsshSubs).toBeVisible();

    // Switch back to GitHub
    await page.locator("#tab-bar button", { hasText: "GitHub" }).click();
    await expect(githubSubs).toBeVisible();
    await expect(claudeSubs).toBeHidden();
    await expect(skillsshSubs).toBeHidden();
  });

  test("GitHub tab shows Daily sub-tab as active by default", async ({
    page,
  }) => {
    const dailyBtn = page
      .locator("#github-subtabs button", { hasText: "Daily" })
      .first();
    const historyBtn = page.locator("#github-subtabs button", {
      hasText: "History",
    });

    // Daily should have the active blue styling
    await expect(dailyBtn).toHaveClass(/bg-blue-100/);
    // History should have the inactive white/gray styling
    await expect(historyBtn).toHaveClass(/bg-white/);
  });

  test("GitHub sub-tabs contain Daily and History", async ({ page }) => {
    const subtabs = page.locator("#github-subtabs button");
    await expect(subtabs).toHaveCount(2);
    await expect(subtabs.nth(0)).toHaveText("Daily");
    await expect(subtabs.nth(1)).toHaveText("History");
  });

  test("AI Tools sub-tabs contain all expected types", async ({ page }) => {
    await page.locator("#tab-bar button", { hasText: "AI Tools" }).click();
    const subtabs = page.locator("#claude-subtabs button");
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
    await page
      .locator("#tab-bar button", { hasText: "Agent Skills" })
      .click();
    const subtabs = page.locator("#skillssh-subtabs button");
    const expectedLabels = ["All Time", "Trending (24h)", "Hot", "Official"];
    await expect(subtabs).toHaveCount(expectedLabels.length);
    for (let i = 0; i < expectedLabels.length; i++) {
      await expect(subtabs.nth(i)).toHaveText(expectedLabels[i]);
    }
  });

  test("AI Tools table headers render correctly", async ({ page }) => {
    // Inject mock data so the table renders with headers
    await page.evaluate(() => {
      (window as any).allItems = [
        {
          source_type: "aitmpl_trending",
          title: "Test Component",
          url: "https://example.com",
          score: 1,
          summary: "Category: Test | Today: +5 | Week: 100 | Month: 500 | Total: 2000",
          tags: [],
        },
      ];
      (window as any).currentTab = "claude";
      (window as any).claudeType = "all";
      (window as any).renderTable("claude");
    });

    const headers = page.locator("#items .grid").first();
    await expect(headers).toContainText("#");
    await expect(headers).toContainText("Component");
    await expect(headers).toContainText("Today");
    await expect(headers).toContainText("Week");
    await expect(headers).toContainText("Month");
    await expect(headers).toContainText("Total");
  });

  test("Agent Skills table headers render correctly", async ({ page }) => {
    // Inject mock data so the table renders with headers
    await page.evaluate(() => {
      (window as any).allItems = [
        {
          source_type: "skillssh_all",
          title: "Test Skill",
          url: "https://example.com",
          score: 1,
          summary: "Source: test | GEN: SAFE | SOCKET: LOW | SNYK: 0 alerts | Installs: 1234",
          tags: [],
        },
      ];
      (window as any).currentTab = "skillssh";
      (window as any).skillsshType = "all";
      (window as any).renderTable("skillssh");
    });

    const headers = page.locator("#items .grid").first();
    await expect(headers).toContainText("#");
    await expect(headers).toContainText("GEN");
    await expect(headers).toContainText("SOCKET");
    await expect(headers).toContainText("SNYK");
    await expect(headers).toContainText("Installs");
  });
});
