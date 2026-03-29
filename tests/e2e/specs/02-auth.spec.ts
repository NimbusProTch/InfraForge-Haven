import { test, expect } from "@playwright/test";
import { loginWithKeycloak } from "../helpers/auth";

test.describe("Authentication Flow", () => {
  test("Keycloak login → redirects to dashboard", async ({ page }) => {
    await loginWithKeycloak(page);
    await expect(page).toHaveURL(/\/dashboard/);
    // Dashboard heading or any content should be visible
    await expect(page.locator("h1, h2").first()).toBeVisible({ timeout: 10_000 });
  });

  test("unauthenticated access to /tenants redirects to signin", async ({ page }) => {
    await page.context().clearCookies();
    await page.goto("/tenants");
    await page.waitForURL(/\/(auth\/signin|realms)/, { timeout: 10_000 });
  });

  test("after login, sidebar shows user info", async ({ page }) => {
    await loginWithKeycloak(page);
    // Sidebar should have a logout button or user avatar
    await expect(page.locator('[title="Sign out"], button:has-text("Sign out"), button:has-text("Log out")').first()).toBeVisible({ timeout: 10_000 });
  });

  test("after login, can navigate to projects", async ({ page }) => {
    await loginWithKeycloak(page);
    await page.locator('a[href="/tenants"]').click();
    await expect(page).toHaveURL(/\/tenants/);
    await expect(page.getByRole("heading", { name: /Projects/i }).first()).toBeVisible({ timeout: 5_000 });
  });
});
