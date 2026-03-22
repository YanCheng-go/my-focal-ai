import { test, expect } from "@playwright/test";

// Tour tests run against the static HTML files (Vercel deployment), not the
// FastAPI server. We serve static/ on a local HTTP server in CI via the
// check-static-pages job, but for tour tests we use a file URL directly.
const STATIC_INDEX = `file://${process.cwd()}/static/index.html`;

test.describe("Onboarding tour", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(STATIC_INDEX);
    await page.evaluate(() => {
      localStorage.removeItem("myfocalai_toured");
      localStorage.setItem("myfocalai_welcomed", "true");
    });
    // Reload so localStorage takes effect before scripts run
    await page.goto(STATIC_INDEX);
    await page.waitForLoadState("networkidle");
  });

  test("tour help button is visible in nav", async ({ page }) => {
    const btn = page.locator("#tour-help-btn");
    await expect(btn).toBeVisible();
    await expect(btn).toHaveAttribute("title", "Take a tour");
  });

  test("clicking help button starts the tour", async ({ page }) => {
    await page.locator("#tour-help-btn").click();

    await expect(page.locator("#tour-overlay")).toBeVisible();
    await expect(page.locator("#tour-tooltip")).toBeVisible();
    await expect(page.locator("#tour-tooltip")).toContainText("Search");
    await expect(page.locator("#tour-tooltip")).toContainText("1 / 5");
  });

  test("Next button advances through steps", async ({ page }) => {
    await page.locator("#tour-help-btn").click();
    await expect(page.locator("#tour-tooltip")).toContainText("1 / 5");

    await page.locator("#tour-tooltip button", { hasText: "Next" }).click();
    await expect(page.locator("#tour-tooltip")).toContainText("Filters");
    await expect(page.locator("#tour-tooltip")).toContainText("2 / 5");
  });

  test("Skip button ends tour early", async ({ page }) => {
    await page.locator("#tour-help-btn").click();
    await expect(page.locator("#tour-overlay")).toBeVisible();

    await page.locator("#tour-tooltip button", { hasText: "Skip" }).click();

    await expect(page.locator("#tour-overlay")).toHaveCount(0);
    await expect(page.locator("#tour-tooltip")).toHaveCount(0);
  });

  test("Escape key closes the tour", async ({ page }) => {
    await page.locator("#tour-help-btn").click();
    await expect(page.locator("#tour-overlay")).toBeVisible();

    await page.keyboard.press("Escape");

    await expect(page.locator("#tour-overlay")).toHaveCount(0);
  });

  test("tour sets localStorage flag on completion", async ({ page }) => {
    await page.locator("#tour-help-btn").click();
    await page.locator("#tour-tooltip button", { hasText: "Skip" }).click();

    const toured = await page.evaluate(() =>
      localStorage.getItem("myfocalai_toured")
    );
    expect(toured).toBe("true");
  });

  test("clicking overlay closes the tour", async ({ page }) => {
    await page.locator("#tour-help-btn").click();
    await expect(page.locator("#tour-overlay")).toBeVisible();

    await page.locator("#tour-overlay").click({ position: { x: 5, y: 5 } });

    await expect(page.locator("#tour-overlay")).toHaveCount(0);
  });

  test("Done button on last step ends tour", async ({ page }) => {
    await page.locator("#tour-help-btn").click();
    await expect(page.locator("#tour-tooltip")).toBeVisible();

    // Advance through all steps — wait for step counter to change between clicks
    for (let i = 0; i < 10; i++) {
      const done = page.locator("#tour-tooltip button", { hasText: "Done" });
      if (await done.isVisible().catch(() => false)) break;
      const next = page.locator("#tour-tooltip button", { hasText: "Next" });
      if (!(await next.isVisible().catch(() => false))) break;
      // Read current step label before clicking
      const label = await page.locator("#tour-tooltip").textContent();
      await next.click();
      // Wait for step to change (new content rendered after 200ms delay)
      await expect(page.locator("#tour-tooltip")).not.toContainText(
        label?.match(/\d+ \/ \d+/)?.[0] || "impossible",
        { timeout: 3000 }
      );
    }

    const doneBtn = page.locator("#tour-tooltip button", { hasText: "Done" });
    await expect(doneBtn).toBeVisible({ timeout: 5000 });
    await doneBtn.click();
    await expect(page.locator("#tour-overlay")).toHaveCount(0);
  });

  test("tour restores element styles after closing", async ({ page }) => {
    // Capture original search box styles
    const originalStyles = await page.evaluate(() => {
      const el = document.querySelector("#search") as HTMLElement;
      if (!el) return { zIndex: "", boxShadow: "" };
      return { zIndex: el.style.zIndex, boxShadow: el.style.boxShadow };
    });

    await page.locator("#tour-help-btn").click();
    await expect(page.locator("#tour-tooltip")).toContainText("1 / 5");
    await page.locator("#tour-tooltip button", { hasText: "Skip" }).click();

    const afterStyles = await page.evaluate(() => {
      const el = document.querySelector("#search") as HTMLElement;
      if (!el) return { zIndex: "", boxShadow: "" };
      return { zIndex: el.style.zIndex, boxShadow: el.style.boxShadow };
    });

    expect(afterStyles.zIndex).toBe(originalStyles.zIndex);
    expect(afterStyles.boxShadow).toBe(originalStyles.boxShadow);
  });

  test("tooltip has dialog role for accessibility", async ({ page }) => {
    await page.locator("#tour-help-btn").click();
    await expect(page.locator("#tour-tooltip")).toHaveAttribute(
      "role",
      "dialog"
    );
  });

  test("?tour=1 query param auto-starts tour", async ({ page }) => {
    await page.goto(STATIC_INDEX + "?tour=1");
    await expect(page.locator("#tour-overlay")).toBeVisible({ timeout: 3000 });
    await expect(page.locator("#tour-tooltip")).toBeVisible();
  });
});
