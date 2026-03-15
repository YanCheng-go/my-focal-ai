import { defineConfig, devices } from "@playwright/test";

// Use Chromium for all projects — we're testing responsive layout, not cross-browser.
// Override defaultBrowserType from device descriptors that default to webkit.
const chromium = { channel: "chromium" as const };

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  retries: 0,
  reporter: [["html", { open: "never" }]],
  use: {
    baseURL: "http://localhost:8000",
    screenshot: "only-on-failure",
  },
  expect: {
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.01,
    },
  },
  projects: [
    {
      name: "mobile-small",
      use: {
        ...devices["iPhone SE"],
        defaultBrowserType: "chromium",
      },
    },
    {
      name: "mobile",
      use: {
        ...devices["iPhone 15"],
        defaultBrowserType: "chromium",
      },
    },
    {
      name: "mobile-large",
      use: {
        ...devices["iPhone 15 Pro Max"],
        defaultBrowserType: "chromium",
      },
    },
    {
      name: "tablet",
      use: {
        ...devices["iPad Mini"],
        defaultBrowserType: "chromium",
      },
    },
    {
      name: "desktop",
      use: { viewport: { width: 1280, height: 720 } },
    },
    {
      name: "desktop-wide",
      use: { viewport: { width: 1920, height: 1080 } },
    },
  ],
});
