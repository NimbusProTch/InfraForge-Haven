import { type Page } from "@playwright/test";

const KC_USER = process.env.KC_USER || "testuser";
const KC_PASS = process.env.KC_PASS || "test123456";

/**
 * Log in through Keycloak OAuth flow.
 * Clicks "Sign in with Keycloak" → fills credentials → returns to app.
 */
export async function loginWithKeycloak(page: Page) {
  await page.goto("/auth/signin");
  await page.waitForLoadState("networkidle");

  // Click Keycloak sign-in button
  const kcButton = page.getByRole("button", { name: /sso|keycloak/i });
  await kcButton.click();

  // Wait for Keycloak login form
  await page.waitForURL(/realms\/haven/, { timeout: 10_000 });

  // Fill credentials
  await page.fill("#username", KC_USER);
  await page.fill("#password", KC_PASS);
  await page.click("#kc-login");

  // Wait for redirect back to app
  await page.waitForURL(/\/(dashboard|tenants)/, { timeout: 15_000 });
}

/**
 * Ensure we're logged in — if already on a page with content, skip.
 * Otherwise do full Keycloak login.
 */
export async function ensureLoggedIn(page: Page) {
  await page.goto("/dashboard");
  const url = page.url();
  if (url.includes("/auth/signin") || url.includes("realms/haven")) {
    await loginWithKeycloak(page);
  }
}
