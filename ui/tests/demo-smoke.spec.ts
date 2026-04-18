/**
 * Demo smoke — verifies iyziops UI is reachable + login works.
 * Prerequisite for the full demo-full-journey.spec.ts that will follow.
 */
import { test, expect } from "@playwright/test";

test.describe("iyziops UI smoke", () => {
  test.setTimeout(60_000);

  test("iyziops.com reachable and redirects to signin", async ({ page }) => {
    const res = await page.goto("https://iyziops.com", { waitUntil: "networkidle" });
    expect(res?.status()).toBeLessThan(500);
    // Either already at dashboard (cached session) or signin page
    const url = page.url();
    expect(url).toMatch(/iyziops\.com\/(auth|dashboard|organizations|tenants)/);
  });

  test("login as testuser reaches dashboard", async ({ page }) => {
    await page.goto("https://iyziops.com", { waitUntil: "networkidle" });
    // Navigate to signin if not already there
    if (!page.url().includes("/auth/signin")) {
      await page.goto("https://iyziops.com/auth/signin", { waitUntil: "networkidle" });
    }
    // Click Keycloak sign-in button (label varies: "Sign in with Keycloak", "Keycloak", etc.)
    const kcBtn = page.getByRole("button", { name: /keycloak|sign in/i }).first();
    await kcBtn.click({ timeout: 10_000 }).catch(() => {});
    // Wait for Keycloak redirect
    await page.waitForURL(/keycloak\.iyziops\.com/, { timeout: 15_000 }).catch(() => {});
    if (page.url().includes("keycloak")) {
      await page.fill("#username", "testuser");
      await page.fill("#password", "test123456");
      await page.click("#kc-login");
      await page.waitForURL(/iyziops\.com\/(dashboard|organizations|tenants)/, { timeout: 20_000 });
    }
    expect(page.url()).toMatch(/iyziops\.com\/(dashboard|organizations|tenants)/);
  });

  test("api.iyziops.com /health returns 200", async ({ request }) => {
    const r = await request.get("https://api.iyziops.com/health");
    expect(r.status()).toBe(200);
    const json = await r.json();
    expect(json.status).toBe("ok");
  });
});
