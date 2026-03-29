import { test, expect } from "@playwright/test";
import { loginWithKeycloak } from "../helpers/auth";

test.describe("Authentication Flow", () => {
  test("Keycloak login → redirects to dashboard", async ({ page }) => {
    await loginWithKeycloak(page);
    await expect(page).toHaveURL(/\/dashboard/);
    // Dashboard should show stats
    await expect(page.locator("h1, h2, h3").first()).toBeVisible({ timeout: 10_000 });
  });

  test("unauthenticated access to /tenants redirects to signin", async ({ page }) => {
    // Clear cookies first
    await page.context().clearCookies();
    await page.goto("/tenants");
    // Should redirect to signin
    await page.waitForURL(/\/(auth\/signin|realms)/, { timeout: 10_000 });
  });

  test("after login, sidebar shows user email", async ({ page }) => {
    await loginWithKeycloak(page);
    await expect(page.getByText(/test@haven.nl|testdev/)).toBeVisible({ timeout: 10_000 });
  });

  test("after login, navigation works", async ({ page }) => {
    await loginWithKeycloak(page);

    // Navigate to Projects
    await page.getByRole("link", { name: /projects/i }).click();
    await expect(page).toHaveURL(/\/tenants/);

    // Navigate to Dashboard
    await page.getByRole("link", { name: /home/i }).click();
    await expect(page).toHaveURL(/\/dashboard/);
  });
});
