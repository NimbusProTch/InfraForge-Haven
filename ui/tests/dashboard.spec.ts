import { test, expect } from "@playwright/test";
import { mockSession, mockGet, TENANT, APP, DEPLOYMENT, CLUSTER_HEALTH } from "./helpers";

test.describe("Dashboard", () => {
  test.beforeEach(async ({ page }) => {
    await mockSession(page);
    await mockGet(page, "/tenants", [TENANT]);
    await mockGet(page, "/health/cluster", CLUSTER_HEALTH);
    await mockGet(page, `/tenants/${TENANT.slug}/apps`, [APP]);
    await mockGet(page, `/tenants/${TENANT.slug}/apps/${APP.slug}/deployments`, [DEPLOYMENT]);
  });

  test("renders welcome message", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page.locator("text=Welcome back")).toBeVisible();
  });

  test("shows stat cards", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page.getByText("Projects", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Applications", { exact: true })).toBeVisible();
  });

  test("shows cluster health status", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page.locator("text=Cluster")).toBeVisible();
  });

  test("shows quick action buttons", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page.locator("text=New Project")).toBeVisible();
    await expect(page.locator("text=View All Projects")).toBeVisible();
  });

  test("shows recent projects", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page.locator(`text=${TENANT.name}`)).toBeVisible();
  });

  test("empty state when no projects", async ({ page }) => {
    await mockGet(page, "/tenants", []);
    await page.goto("/dashboard");
    await expect(page.locator("text=No projects yet")).toBeVisible();
  });
});
