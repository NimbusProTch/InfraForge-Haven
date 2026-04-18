import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./specs",
  outputDir: "./results",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [
    ["list"],
    ["html", { outputFolder: "./report", open: "never" }],
  ],
  use: {
    baseURL: process.env.BASE_URL || "http://localhost:3001",
    screenshot: "only-on-failure",
    trace: "on-first-retry",
  },
  projects: [
    // 1. Auth setup — run once, save session
    {
      name: "auth-setup",
      testDir: "./fixtures",
      testMatch: "auth.setup.ts",
    },
    // 2. Smoke + API tests — no auth needed
    {
      name: "smoke",
      testMatch: "01-smoke.spec.ts",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "api-crud",
      testMatch: "03-api-crud.spec.ts",
      use: { ...devices["Desktop Chrome"] },
    },
    // 3. Auth tests — needs fresh browser (no stored state)
    {
      name: "auth",
      testMatch: "02-auth.spec.ts",
      use: { ...devices["Desktop Chrome"] },
    },
    // 4. UI tests — use saved auth state
    {
      name: "ui",
      testMatch: /(0[4-9]|[1-9][0-9])-.+\.spec\.ts/,
      dependencies: ["auth-setup"],
      use: {
        ...devices["Desktop Chrome"],
        storageState: "fixtures/.auth-state.json",
      },
    },
  ],
});
