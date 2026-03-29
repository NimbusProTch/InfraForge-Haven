import { test, expect } from "@playwright/test";
import { getApiToken, apiCall, cleanupTenant } from "../helpers/api";

const TENANT_NAME = "PW Tenant Test";
const TENANT_SLUG = "pw-tenant-test";

test.describe("UI — Tenant CRUD Flow", () => {
  test.beforeAll(async ({ request }) => {
    const token = await getApiToken(request);
    // Force cleanup — delete apps first, then tenant
    try {
      const apps = await (await apiCall(request, "GET", `/tenants/${TENANT_SLUG}/apps`, token)).json();
      for (const app of apps) {
        await apiCall(request, "DELETE", `/tenants/${TENANT_SLUG}/apps/${app.slug}`, token);
      }
    } catch { /* tenant may not exist */ }
    await cleanupTenant(request, token, TENANT_SLUG);
  });

  test.afterAll(async ({ request }) => {
    const token = await getApiToken(request);
    try {
      const apps = await (await apiCall(request, "GET", `/tenants/${TENANT_SLUG}/apps`, token)).json();
      for (const app of apps) {
        await apiCall(request, "DELETE", `/tenants/${TENANT_SLUG}/apps/${app.slug}`, token);
      }
    } catch { /* ignore */ }
    await cleanupTenant(request, token, TENANT_SLUG);
  });

  test("dashboard loads after auth", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");
    expect(page.url()).not.toContain("/auth/signin");
    await expect(page.locator("h1, h2, h3").first()).toBeVisible({ timeout: 10_000 });
  });

  test("navigate to projects page", async ({ page }) => {
    await page.goto("/tenants");
    await page.waitForLoadState("networkidle");
    // Should see Projects heading (exact)
    await expect(page.getByText("Projects", { exact: true }).first()).toBeVisible({ timeout: 5_000 });
  });

  test("create new tenant via UI", async ({ page }) => {
    await page.goto("/tenants/new");
    await page.waitForLoadState("networkidle");

    await page.locator('input[placeholder="Gemeente Utrecht"]').fill(TENANT_NAME);
    await page.waitForTimeout(500);
    await page.locator('input[placeholder="gemeente-utrecht"]').clear();
    await page.locator('input[placeholder="gemeente-utrecht"]').fill(TENANT_SLUG);

    await page.getByRole("button", { name: /create/i }).click();
    await page.waitForURL(`**/tenants/${TENANT_SLUG}`, { timeout: 15_000 });
    await expect(page.getByRole("heading", { name: TENANT_NAME })).toBeVisible({ timeout: 5_000 });
  });

  test("tenant detail shows tabs and info", async ({ page }) => {
    await page.goto(`/tenants/${TENANT_SLUG}`);
    await page.waitForLoadState("networkidle");

    await expect(page.getByRole("heading", { name: TENANT_NAME })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(`tenant-${TENANT_SLUG}`)).toBeVisible();
    await expect(page.getByRole("tab", { name: /Applications/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /Services/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /Members/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /Usage/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /Audit/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /Privacy/i })).toBeVisible();
  });

  test("empty state for apps", async ({ page }) => {
    await page.goto(`/tenants/${TENANT_SLUG}`);
    await page.waitForLoadState("networkidle");
    await expect(page.getByText("No applications yet.")).toBeVisible({ timeout: 5_000 });
  });

  test("tenant in projects list", async ({ page }) => {
    await page.goto("/tenants");
    await page.waitForLoadState("networkidle");
    await expect(page.getByText(TENANT_NAME).first()).toBeVisible({ timeout: 5_000 });
  });
});
