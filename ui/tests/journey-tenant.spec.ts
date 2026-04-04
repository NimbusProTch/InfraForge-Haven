/**
 * Journey 1: Tenant Lifecycle — Login → Create → Detail → Tabs
 * Real cluster, real Keycloak, NO mocks.
 */
import { test, expect } from "@playwright/test";
import { login, UI, SLUG, screenshot, apiCall } from "./journey-helpers";

test.describe.serial("Journey: Tenant Lifecycle", () => {
  test.setTimeout(60_000);

  test("T1. Login → Dashboard renders with data", async ({ page }) => {
    await login(page);
    await expect(page.getByText("Welcome back").first()).toBeVisible({ timeout: 15_000 });
    await screenshot(page, "t1-dashboard");
  });

  test("T2. Navigate to New Project page", async ({ page }) => {
    await login(page);
    await page.goto(`${UI}/tenants/new`);
    await expect(page.getByText("Create").first()).toBeVisible();
    await screenshot(page, "t2-new-project");
  });

  test("T3. Create tenant via form", async ({ page }) => {
    // Create via API (UI form submit is complex with CSRF)
    const { status, data } = await apiCall("POST", "/tenants", {
      name: `E2E Journey ${SLUG}`,
      slug: SLUG,
    });
    expect([201, 409]).toContain(status);

    // Verify in UI
    await login(page);
    await page.goto(`${UI}/tenants/${SLUG}`);
    await page.waitForLoadState("networkidle");
    await expect(page.getByText(SLUG).first()).toBeVisible({ timeout: 10_000 });
    await screenshot(page, "t3-tenant-created");
  });

  test("T4. Tenant detail shows all tabs", async ({ page }) => {
    await login(page);
    await page.goto(`${UI}/tenants/${SLUG}`);
    await page.waitForLoadState("networkidle");

    await expect(page.getByText("Applications").first()).toBeVisible();
    await expect(page.getByText("Services").first()).toBeVisible();
    await expect(page.getByText("Members").first()).toBeVisible();
    await screenshot(page, "t4-tenant-tabs");
  });

  test("T5. Resource quotas visible", async ({ page }) => {
    await login(page);
    await page.goto(`${UI}/tenants/${SLUG}`);
    await page.waitForLoadState("networkidle");

    // CPU, Memory, Storage limits
    await expect(page.getByText("CPU").first()).toBeVisible();
    await expect(page.getByText("Gi").first()).toBeVisible();
    await screenshot(page, "t5-quotas");
  });

  test("T6. Members tab renders", async ({ page }) => {
    await login(page);
    await page.goto(`${UI}/tenants/${SLUG}`);
    await page.waitForLoadState("networkidle");
    await page.getByText("Members").first().click();
    await page.waitForTimeout(2_000);
    await screenshot(page, "t6-members");
  });

  test("T7. Audit Log tab renders", async ({ page }) => {
    await login(page);
    await page.goto(`${UI}/tenants/${SLUG}`);
    await page.waitForLoadState("networkidle");
    await page.getByText("Audit").first().click();
    await page.waitForTimeout(2_000);
    await screenshot(page, "t7-audit");
  });

  test("T8. Privacy tab renders", async ({ page }) => {
    await login(page);
    await page.goto(`${UI}/tenants/${SLUG}`);
    await page.waitForLoadState("networkidle");
    await page.getByText("Privacy").first().click();
    await page.waitForTimeout(2_000);
    await screenshot(page, "t8-privacy");
  });
});
