import { test, expect, request as apiRequest } from "@playwright/test";
import { getApiToken, apiCall, cleanupTenant } from "../helpers/api";

const TENANT_SLUG = "pw-app-flow";
const APP_SLUG = "pw-test-app";

test.describe("UI — App CRUD Flow", () => {
  test.beforeAll(async () => {
    const ctx = await apiRequest.newContext();
    const token = await getApiToken(ctx);
    await cleanupTenant(ctx, token, TENANT_SLUG);
    // Create tenant + app via API so we have stable slugs
    await apiCall(ctx, "POST", "/tenants", token, { name: "App Flow Test", slug: TENANT_SLUG });
    await apiCall(ctx, "POST", `/tenants/${TENANT_SLUG}/apps`, token, {
      name: "PW Test App", slug: APP_SLUG,
      repo_url: "https://github.com/test/sample", branch: "main", port: 3000,
    });
    await ctx.dispose();
  });

  test.afterAll(async () => {
    const ctx = await apiRequest.newContext();
    const token = await getApiToken(ctx);
    await cleanupTenant(ctx, token, TENANT_SLUG);
    await ctx.dispose();
  });

  test("new app page loads", async ({ page }) => {
    await page.goto(`/tenants/${TENANT_SLUG}/apps/new`);
    await page.waitForLoadState("networkidle");
    await expect(page.locator('input[placeholder*="My App"]')).toBeVisible();
  });

  test("app detail page has all 9 tabs", async ({ page }) => {
    await page.goto(`/tenants/${TENANT_SLUG}/apps/${APP_SLUG}`);
    await page.waitForLoadState("networkidle");

    const expectedTabs = ["Deployments", "Observability", "Logs", "Environments", "Domains", "Jobs", "Storage", "Canary", "Settings"];
    for (const tab of expectedTabs) {
      await expect(page.getByRole("tab", { name: new RegExp(tab, "i") })).toBeVisible({ timeout: 3_000 });
    }
  });

  test("each tab renders without JS error", async ({ page }) => {
    await page.goto(`/tenants/${TENANT_SLUG}/apps/${APP_SLUG}`);
    await page.waitForLoadState("networkidle");

    const tabs = ["Environments", "Domains", "Jobs", "Storage", "Canary", "Settings"];
    for (const tab of tabs) {
      await page.getByRole("tab", { name: new RegExp(tab, "i") }).click();
      await page.waitForTimeout(1000);
      const body = await page.locator("body").textContent();
      expect(body).not.toContain("Application error");
      expect(body).not.toContain("Unhandled Runtime Error");
    }
  });

  test("environments tab — empty state", async ({ page }) => {
    await page.goto(`/tenants/${TENANT_SLUG}/apps/${APP_SLUG}`);
    await page.waitForLoadState("networkidle");
    await page.getByRole("tab", { name: /environments/i }).click();
    await expect(page.getByText(/no environments/i)).toBeVisible({ timeout: 5_000 });
  });

  test("domains tab — empty state", async ({ page }) => {
    await page.goto(`/tenants/${TENANT_SLUG}/apps/${APP_SLUG}`);
    await page.waitForLoadState("networkidle");
    await page.getByRole("tab", { name: /domains/i }).click();
    await expect(page.getByText(/no custom domains/i)).toBeVisible({ timeout: 5_000 });
  });

  test("jobs tab — empty state", async ({ page }) => {
    await page.goto(`/tenants/${TENANT_SLUG}/apps/${APP_SLUG}`);
    await page.waitForLoadState("networkidle");
    await page.getByRole("tab", { name: /jobs/i }).click();
    await expect(page.getByText(/no scheduled jobs/i)).toBeVisible({ timeout: 5_000 });
  });

  test("storage tab — empty state", async ({ page }) => {
    await page.goto(`/tenants/${TENANT_SLUG}/apps/${APP_SLUG}`);
    await page.waitForLoadState("networkidle");
    await page.getByRole("tab", { name: /storage/i }).click();
    await expect(page.getByText(/no persistent volumes/i)).toBeVisible({ timeout: 5_000 });
  });

  test("canary tab — disabled state", async ({ page }) => {
    await page.goto(`/tenants/${TENANT_SLUG}/apps/${APP_SLUG}`);
    await page.waitForLoadState("networkidle");
    await page.getByRole("tab", { name: /canary/i }).click();
    await expect(page.getByText(/enable canary|disabled/i).first()).toBeVisible({ timeout: 5_000 });
  });
});
