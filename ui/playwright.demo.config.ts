import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for demo tests (hits live https://iyziops.com — no local webServer).
 * Separate from playwright.config.ts which spins up local Next.js dev server.
 */
export default defineConfig({
  testDir: "./tests",
  testMatch: "demo-*.spec.ts",
  timeout: 90_000,
  retries: 1,
  workers: 1,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report-demo" }]],
  use: {
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    viewport: { width: 1280, height: 800 },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
