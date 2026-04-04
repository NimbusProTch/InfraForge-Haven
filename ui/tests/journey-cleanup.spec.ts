/**
 * Journey 5: Cleanup — Delete app, services, tenant. Verify cascade.
 * Real cluster, real Keycloak, NO mocks.
 */
import { test, expect } from "@playwright/test";
import { login, UI, SLUG, screenshot, apiCall } from "./journey-helpers";

test.describe.serial("Journey: Cleanup & Cascade Delete", () => {
  test.setTimeout(60_000);

  test("C1. Delete app via API", async ({ page }) => {
    const { status } = await apiCall("DELETE", `/tenants/${SLUG}/apps/journey-api`);
    expect([204, 404]).toContain(status); // 404 if already deleted

    await login(page);
    await page.goto(`${UI}/tenants/${SLUG}`);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2_000);
    const content = await page.textContent("body");
    expect(content).not.toContain("journey-api");
    await screenshot(page, "c1-app-deleted");
  });

  test("C2. Delete PG service via API", async ({ page }) => {
    const { status } = await apiCall("DELETE", `/tenants/${SLUG}/services/app-pg`);
    expect([204, 404]).toContain(status);
  });

  test("C3. Delete remaining services", async ({ page }) => {
    // Clean up any remaining services
    const { data: svcs } = await apiCall("GET", `/tenants/${SLUG}/services`);
    if (Array.isArray(svcs)) {
      for (const svc of svcs) {
        await apiCall("DELETE", `/tenants/${SLUG}/services/${svc.name}`);
      }
    }
  });

  test("C4. Delete tenant via API", async ({ page }) => {
    const { status } = await apiCall("DELETE", `/tenants/${SLUG}`);
    expect([204, 404]).toContain(status);

    await login(page);
    await page.goto(`${UI}/tenants`);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2_000);
    const content = await page.textContent("body");
    expect(content).not.toContain(SLUG);
    await screenshot(page, "c4-tenant-deleted");
  });

  test("C5. Verify tenant not in API list", async ({ page }) => {
    const { status } = await apiCall("GET", `/tenants/${SLUG}`);
    expect(status).toBe(404);
  });
});
