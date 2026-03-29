import { test, expect } from "@playwright/test";
import { ensureLoggedIn } from "../helpers/auth";
import { getApiToken, apiCall, cleanupTenant } from "../helpers/api";

const TENANT_SLUG = "pw-app-test";

test.describe("UI — App CRUD Flow", () => {
  test.beforeAll(async ({ request }) => {
    const token = await getApiToken(request);
    await cleanupTenant(request, token, TENANT_SLUG);
    // Create tenant via API for app tests
    await apiCall(request, "POST", "/tenants", token, {
      name: "App Test Project",
      slug: TENANT_SLUG,
    });
  });

  test.afterAll(async ({ request }) => {
    const token = await getApiToken(request);
    await cleanupTenant(request, token, TENANT_SLUG);
  });

  test("navigate to new app page", async ({ page }) => {
    await ensureLoggedIn(page);
    await page.goto(`/tenants/${TENANT_SLUG}/apps/new`);
    await expect(page.getByText(/application name/i)).toBeVisible();
  });

  test("create app via UI", async ({ page }) => {
    await ensureLoggedIn(page);
    await page.goto(`/tenants/${TENANT_SLUG}/apps/new`);

    // Fill app name
    await page.fill('input[placeholder*="My App"]', "E2E Test App");

    // Slug should auto-generate
    await expect(page.locator('input[name="slug"], input[placeholder*="my-app"]')).toHaveValue(/e2e-test-app/i);

    // Enter manual repo URL (click "Enter manually" if needed)
    const manualBtn = page.getByText(/enter manually/i);
    if (await manualBtn.isVisible()) await manualBtn.click();

    // Fill repo URL
    const repoInput = page.locator('input[placeholder*="github.com"]').first();
    await repoInput.fill("https://github.com/test/sample-app");

    // Submit
    await page.getByRole("button", { name: /create application/i }).click();

    // Should redirect to app detail
    await page.waitForURL(`**/apps/e2e-test-app`, { timeout: 10_000 });
  });

  test("app detail page loads with tabs", async ({ page }) => {
    await ensureLoggedIn(page);
    await page.goto(`/tenants/${TENANT_SLUG}/apps/e2e-test-app`);
    await page.waitForLoadState("networkidle");

    // Check tabs
    await expect(page.getByRole("tab", { name: /deployments/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /observability/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /logs/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /environments/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /domains/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /jobs/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /storage/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /canary/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /settings/i })).toBeVisible();
  });

  test("settings tab — update env vars", async ({ page }) => {
    await ensureLoggedIn(page);
    await page.goto(`/tenants/${TENANT_SLUG}/apps/e2e-test-app`);
    await page.waitForLoadState("networkidle");

    await page.getByRole("tab", { name: /settings/i }).click();

    // Look for Environment tab within settings
    const envTab = page.getByRole("tab", { name: /environment/i });
    if (await envTab.isVisible()) {
      await envTab.click();
      // Should see env var editor
      await expect(page.getByText(/environment variables/i)).toBeVisible();
    }
  });

  test("environments tab — shows empty state", async ({ page }) => {
    await ensureLoggedIn(page);
    await page.goto(`/tenants/${TENANT_SLUG}/apps/e2e-test-app`);
    await page.waitForLoadState("networkidle");

    await page.getByRole("tab", { name: /environments/i }).click();
    await expect(page.getByText(/no environments/i)).toBeVisible({ timeout: 5_000 });
  });

  test("domains tab — shows empty state", async ({ page }) => {
    await ensureLoggedIn(page);
    await page.goto(`/tenants/${TENANT_SLUG}/apps/e2e-test-app`);
    await page.waitForLoadState("networkidle");

    await page.getByRole("tab", { name: /domains/i }).click();
    await expect(page.getByText(/no custom domains/i)).toBeVisible({ timeout: 5_000 });
  });

  test("jobs tab — shows empty state", async ({ page }) => {
    await ensureLoggedIn(page);
    await page.goto(`/tenants/${TENANT_SLUG}/apps/e2e-test-app`);
    await page.waitForLoadState("networkidle");

    await page.getByRole("tab", { name: /jobs/i }).click();
    await expect(page.getByText(/no scheduled jobs/i)).toBeVisible({ timeout: 5_000 });
  });

  test("storage tab — shows empty state", async ({ page }) => {
    await ensureLoggedIn(page);
    await page.goto(`/tenants/${TENANT_SLUG}/apps/e2e-test-app`);
    await page.waitForLoadState("networkidle");

    await page.getByRole("tab", { name: /storage/i }).click();
    await expect(page.getByText(/no persistent volumes/i)).toBeVisible({ timeout: 5_000 });
  });

  test("canary tab — shows disabled state", async ({ page }) => {
    await ensureLoggedIn(page);
    await page.goto(`/tenants/${TENANT_SLUG}/apps/e2e-test-app`);
    await page.waitForLoadState("networkidle");

    await page.getByRole("tab", { name: /canary/i }).click();
    await expect(page.getByText(/disabled|enable canary/i)).toBeVisible({ timeout: 5_000 });
  });
});
