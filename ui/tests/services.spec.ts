import { test, expect } from "@playwright/test";
import { mockSession, mockGet, TENANT, SERVICE_PG, SERVICE_REDIS } from "./helpers";

test.describe("Managed Services", () => {
  test.beforeEach(async ({ page }) => {
    await mockSession(page);
    await mockGet(page, `/tenants/${TENANT.slug}`, TENANT);
    await mockGet(page, `/tenants/${TENANT.slug}/apps`, []);
    await mockGet(page, `/tenants/${TENANT.slug}/services`, [SERVICE_PG, SERVICE_REDIS]);
  });

  test("services tab shows service names", async ({ page }) => {
    await page.goto(`/tenants/${TENANT.slug}`);
    await page.getByText("Services").first().click();
    await expect(page.getByText("app-pg").first()).toBeVisible();
    await expect(page.getByText("app-redis").first()).toBeVisible();
  });

  test("service shows ready status badge", async ({ page }) => {
    await page.goto(`/tenants/${TENANT.slug}`);
    await page.getByText("Services").first().click();
    await expect(page.getByText("ready").first()).toBeVisible();
  });

  test("provisioning service shows warning badge", async ({ page }) => {
    await mockGet(page, `/tenants/${TENANT.slug}/services`, [
      { ...SERVICE_PG, status: "provisioning" },
    ]);
    await page.goto(`/tenants/${TENANT.slug}`);
    await page.getByText("Services").first().click();
    await expect(page.getByText("provisioning").first()).toBeVisible();
  });

  test("failed service shows failed badge", async ({ page }) => {
    await mockGet(page, `/tenants/${TENANT.slug}/services`, [
      { ...SERVICE_PG, status: "failed" },
    ]);
    await page.goto(`/tenants/${TENANT.slug}`);
    await page.getByText("Services").first().click();
    await expect(page.getByText("failed").first()).toBeVisible();
  });
});
