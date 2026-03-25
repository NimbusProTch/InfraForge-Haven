import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "/Users/gaskin/Desktop/gokhan_askin/GitHub/InfraForge-Haven/.claude/worktrees/suspicious-elbakyan/ui/tests",
  timeout: 30_000,
  retries: 0,
  workers: 1, // sequential — Keycloak sessions can conflict
  reporter: "list",

  use: {
    baseURL: "http://localhost:3001",
    headless: true,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
