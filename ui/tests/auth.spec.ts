import { test, expect } from "@playwright/test";

test.describe("Authentication", () => {
  test("login page renders with Haven branding", async ({ page }) => {
    await page.goto("/auth/signin");
    await expect(page.locator("text=Haven Platform")).toBeVisible();
    await expect(page.locator("text=Haven-Compliant")).toBeVisible();
  });

  test("Keycloak sign-in button is visible", async ({ page }) => {
    // Mock providers endpoint
    await page.route("**/api/auth/providers", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          keycloak: { id: "keycloak", name: "Keycloak", type: "oauth", signinUrl: "/api/auth/signin/keycloak" },
        }),
      })
    );

    await page.goto("/auth/signin");
    await expect(page.locator("button:has-text('Keycloak')")).toBeVisible();
  });

  test("EU data sovereignty notice is present", async ({ page }) => {
    await page.goto("/auth/signin");
    await expect(page.locator("text=EU data sovereignty")).toBeVisible();
  });

  test("unauthenticated user is redirected to signin", async ({ page }) => {
    // Mock no session
    await page.route("**/api/auth/session", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({}),
      })
    );

    await page.goto("/dashboard");
    // Should redirect to signin
    await page.waitForURL("**/auth/signin**", { timeout: 10_000 });
  });
});
