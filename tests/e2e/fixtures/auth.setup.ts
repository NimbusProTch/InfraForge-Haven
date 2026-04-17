import { test as setup, expect } from "@playwright/test";

const AUTH_FILE = "fixtures/.auth-state.json";

/**
 * Global setup: login once via Keycloak, save session for all tests.
 */
setup("authenticate via Keycloak", async ({ page }) => {
  await page.goto("/auth/signin");
  await page.waitForLoadState("networkidle");

  // Click Keycloak sign-in
  await page.getByRole("button", { name: /sso|keycloak/i }).click();

  // Wait for Keycloak login form
  await page.waitForURL(/realms\/haven/, { timeout: 10_000 });

  // Fill and submit
  await page.locator("#username").fill(process.env.KC_USER || "testuser");
  await page.locator("#password").fill(process.env.KC_PASS || "test123456");
  await page.locator("#kc-login").click();

  // Wait for redirect back
  await page.waitForURL(/\/(dashboard|tenants)/, { timeout: 15_000 });

  // Verify we're logged in
  await expect(page.locator("body")).toContainText(/.+/);

  // Save auth state
  await page.context().storageState({ path: AUTH_FILE });
});
