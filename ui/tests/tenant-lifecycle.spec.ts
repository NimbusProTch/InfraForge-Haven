import { test, expect } from "@playwright/test";
import { mockSession, mockGet, TENANT, APP, DEPLOYMENT, SERVICE_PG, SERVICE_REDIS } from "./helpers";

test.describe("Tenant Lifecycle", () => {
  test.beforeEach(async ({ page }) => {
    await mockSession(page);
  });

  test("tenant list page renders tenant name", async ({ page }) => {
    await mockGet(page, "/tenants", [TENANT]);
    await page.goto("/tenants");
    await expect(page.getByText(TENANT.name).first()).toBeVisible();
  });

  test("create tenant page renders form", async ({ page }) => {
    await page.goto("/tenants/new");
    await expect(page.getByText("Create").first()).toBeVisible();
  });

  test("tenant detail shows app cards", async ({ page }) => {
    await mockGet(page, `/tenants/${TENANT.slug}`, TENANT);
    await mockGet(page, `/tenants/${TENANT.slug}/apps`, [APP]);
    await mockGet(page, `/tenants/${TENANT.slug}/services`, []);
    await mockGet(page, `/tenants/${TENANT.slug}/apps/${APP.slug}/deployments`, [DEPLOYMENT]);

    await page.goto(`/tenants/${TENANT.slug}`);
    await expect(page.getByText(APP.name).first()).toBeVisible();
  });

  test("tenant detail shows services tab", async ({ page }) => {
    await mockGet(page, `/tenants/${TENANT.slug}`, TENANT);
    await mockGet(page, `/tenants/${TENANT.slug}/apps`, []);
    await mockGet(page, `/tenants/${TENANT.slug}/services`, [SERVICE_PG]);

    await page.goto(`/tenants/${TENANT.slug}`);
    await page.getByText("Services").first().click();
    await expect(page.getByText("app-pg").first()).toBeVisible();
  });

  test("tenant detail shows members tab", async ({ page }) => {
    await mockGet(page, `/tenants/${TENANT.slug}`, TENANT);
    await mockGet(page, `/tenants/${TENANT.slug}/apps`, []);
    await mockGet(page, `/tenants/${TENANT.slug}/services`, []);
    await mockGet(page, `/tenants/${TENANT.slug}/members`, []);

    await page.goto(`/tenants/${TENANT.slug}`);
    const membersTab = page.getByText("Members").first();
    await expect(membersTab).toBeVisible();
  });

  test("empty tenant shows create app button", async ({ page }) => {
    await mockGet(page, `/tenants/${TENANT.slug}`, TENANT);
    await mockGet(page, `/tenants/${TENANT.slug}/apps`, []);
    await mockGet(page, `/tenants/${TENANT.slug}/services`, []);

    await page.goto(`/tenants/${TENANT.slug}`);
    await expect(page.getByText(/New App|Create/i).first()).toBeVisible();
  });
});
