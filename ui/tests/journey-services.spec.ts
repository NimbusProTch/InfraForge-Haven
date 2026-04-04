/**
 * Journey 2: Managed Services — Create → Wait Ready → Credentials → Backup → Delete
 * Real cluster, real Keycloak, NO mocks.
 */
import { test, expect } from "@playwright/test";
import { login, UI, SLUG, screenshot, apiCall, waitFor } from "./journey-helpers";

test.describe.serial("Journey: Managed Services", () => {
  test.setTimeout(120_000);

  // Ensure tenant exists
  test.beforeAll(async () => {
    const { status } = await apiCall("POST", "/tenants", {
      name: `E2E Journey ${SLUG}`,
      slug: SLUG,
    });
    // 201 = created, 409 = already exists — both OK
    expect([201, 409]).toContain(status);
  });

  test("S1. Services tab opens", async ({ page }) => {
    await login(page);
    await page.goto(`${UI}/tenants/${SLUG}`);
    await page.waitForLoadState("networkidle");
    await page.getByText("Services").first().click();
    await screenshot(page, "s1-services-tab");
  });

  test("S2. Create Redis service via API", async ({ page }) => {
    const { status, data } = await apiCall("POST", `/tenants/${SLUG}/services`, {
      name: "app-redis",
      service_type: "redis",
      tier: "dev",
    });
    expect([201, 409]).toContain(status);

    await login(page);
    await page.goto(`${UI}/tenants/${SLUG}`);
    await page.waitForLoadState("networkidle");
    await page.getByText("Services").first().click();
    await expect(page.getByText("app-redis").first()).toBeVisible({ timeout: 5_000 });
    await screenshot(page, "s2-redis-created");
  });

  test("S3. Redis reaches ready status", async ({ page }) => {
    await waitFor(async () => {
      const { data } = await apiCall("GET", `/tenants/${SLUG}/services`);
      const redis = data.find((s: any) => s.name === "app-redis");
      return redis?.status === "ready";
    }, { timeout: 30_000 });

    await login(page);
    await page.goto(`${UI}/tenants/${SLUG}`);
    await page.waitForLoadState("networkidle");
    await page.getByText("Services").first().click();
    await expect(page.getByText("ready").first()).toBeVisible();
    await screenshot(page, "s3-redis-ready");
  });

  test("S4. Create PG service via Everest", async ({ page }) => {
    const { status } = await apiCall("POST", `/tenants/${SLUG}/services`, {
      name: "app-pg",
      service_type: "postgres",
      tier: "dev",
    });
    expect([201, 409]).toContain(status);

    await login(page);
    await page.goto(`${UI}/tenants/${SLUG}`);
    await page.waitForLoadState("networkidle");
    await page.getByText("Services").first().click();
    await expect(page.getByText("app-pg").first()).toBeVisible({ timeout: 5_000 });
    await screenshot(page, "s4-pg-created");
  });

  test("S5. PG reaches ready + credentials available", async ({ page }) => {
    await waitFor(async () => {
      const { data } = await apiCall("GET", `/tenants/${SLUG}/services`);
      const pg = data.find((s: any) => s.name === "app-pg");
      return pg?.status === "ready";
    }, { timeout: 120_000, interval: 10_000 });

    // Verify credentials endpoint works
    const { status, data } = await apiCall("GET", `/tenants/${SLUG}/services/app-pg/credentials`);
    expect(status).toBe(200);
    expect(data.credentials || data).toHaveProperty("DATABASE_URL");

    await login(page);
    await page.goto(`${UI}/tenants/${SLUG}`);
    await page.waitForLoadState("networkidle");
    await page.getByText("Services").first().click();
    await screenshot(page, "s5-pg-ready");
  });

  test("S6. Backup trigger for PG", async ({ page }) => {
    const { status, data } = await apiCall("POST", `/tenants/${SLUG}/services/app-pg/backup`);
    expect(status).toBe(202);
    expect(data.backup_name).toBeTruthy();
    await screenshot(page, "s6-backup-triggered");
  });

  test("S7. List backups returns data", async ({ page }) => {
    const { status, data } = await apiCall("GET", `/tenants/${SLUG}/services/app-pg/backups`);
    expect(status).toBe(200);
    expect(data.backups).toBeDefined();
    expect(data.k8s_available).toBe(true);
  });

  test("S8. Delete Redis service", async ({ page }) => {
    const { status } = await apiCall("DELETE", `/tenants/${SLUG}/services/app-redis`);
    expect(status).toBe(204);

    await login(page);
    await page.goto(`${UI}/tenants/${SLUG}`);
    await page.waitForLoadState("networkidle");
    await page.getByText("Services").first().click();
    await page.waitForTimeout(2_000);
    // Redis should be gone
    const content = await page.textContent("body");
    expect(content).not.toContain("app-redis");
    await screenshot(page, "s8-redis-deleted");
  });
});
