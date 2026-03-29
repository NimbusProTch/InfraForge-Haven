import { test, expect } from "@playwright/test";
import { ensureLoggedIn } from "../helpers/auth";

test.describe("UI — Navigation & Sidebar", () => {
  test.beforeEach(async ({ page }) => {
    await ensureLoggedIn(page);
  });

  test("sidebar has all navigation links", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");

    await expect(page.getByRole("link", { name: /home/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /projects/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /organizations/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /queue/i })).toBeVisible();
  });

  test("organizations page loads", async ({ page }) => {
    await page.goto("/organizations");
    await page.waitForLoadState("networkidle");

    await expect(page.getByText(/organizations/i)).toBeVisible();
  });

  test("queue page loads", async ({ page }) => {
    await page.goto("/platform/queue");
    await page.waitForLoadState("networkidle");

    await expect(page.getByText(/build queue|queue/i)).toBeVisible();
  });

  test("dashboard shows stats cards", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");

    // Should have stat cards
    await expect(page.getByText(/projects/i)).toBeVisible();
    await expect(page.getByText(/applications/i)).toBeVisible();
  });
});
