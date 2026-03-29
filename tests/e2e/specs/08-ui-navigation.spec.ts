import { test, expect } from "@playwright/test";

test.describe("UI — Navigation & Sidebar", () => {
  test("sidebar has navigation links", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");

    // Check sidebar nav links (inside <nav>)
    const nav = page.locator("nav");
    await expect(nav.locator('a[href="/dashboard"]')).toBeVisible();
    await expect(nav.locator('a[href="/tenants"]')).toBeVisible();
  });

  test("organizations page renders", async ({ page }) => {
    await page.goto("/organizations");
    await page.waitForLoadState("networkidle");
    await expect(page.getByRole("heading", { name: "Organizations" })).toBeVisible();
  });

  test("queue page renders", async ({ page }) => {
    await page.goto("/platform/queue");
    await page.waitForLoadState("networkidle");
    await expect(page.getByRole("heading", { name: "Build Queue" })).toBeVisible();
  });

  test("dashboard renders stat cards", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");
    // Check exact stat card labels
    await expect(page.getByText("Projects", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Applications", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Cluster", { exact: true }).first()).toBeVisible();
  });
});
