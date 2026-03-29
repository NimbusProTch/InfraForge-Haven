import { test, expect } from "@playwright/test";
import { loginWithKeycloak, ensureLoggedIn } from "../helpers/auth";
import { getApiToken, cleanupTenant } from "../helpers/api";

const TENANT_SLUG = "pw-ui-test";

test.describe("UI — Tenant CRUD Flow", () => {
  test.beforeAll(async ({ request }) => {
    const token = await getApiToken(request);
    await cleanupTenant(request, token, TENANT_SLUG);
  });

  test.afterAll(async ({ request }) => {
    const token = await getApiToken(request);
    await cleanupTenant(request, token, TENANT_SLUG);
  });

  test("login and see dashboard", async ({ page }) => {
    await loginWithKeycloak(page);
    await expect(page.getByText(/Projects|Applications/i)).toBeVisible({ timeout: 10_000 });
  });

  test("navigate to projects page", async ({ page }) => {
    await ensureLoggedIn(page);
    await page.getByRole("link", { name: /projects/i }).click();
    await expect(page).toHaveURL(/\/tenants/);
    await expect(page.getByText(/Projects/)).toBeVisible();
  });

  test("create new tenant via UI", async ({ page }) => {
    await ensureLoggedIn(page);
    await page.goto("/tenants/new");
    await expect(page.getByText(/Organization name/i)).toBeVisible();

    // Fill form
    await page.fill('input[placeholder*="Gemeente"]', "PW UI Test");
    // Slug should auto-generate
    const slugInput = page.locator('input[placeholder*="gemeente-utrecht"]');
    await expect(slugInput).toHaveValue(/pw-ui-test/i);

    // Clear and set exact slug
    await slugInput.clear();
    await slugInput.fill(TENANT_SLUG);

    // Submit
    await page.getByRole("button", { name: /create tenant/i }).click();

    // Should redirect to tenant detail
    await page.waitForURL(`**/tenants/${TENANT_SLUG}`, { timeout: 10_000 });
    await expect(page.getByText("PW UI Test")).toBeVisible();
  });

  test("tenant detail shows correct info", async ({ page }) => {
    await ensureLoggedIn(page);
    await page.goto(`/tenants/${TENANT_SLUG}`);
    await page.waitForLoadState("networkidle");

    // Check header
    await expect(page.getByText("PW UI Test")).toBeVisible();
    await expect(page.getByText(`tenant-${TENANT_SLUG}`)).toBeVisible();

    // Check tabs exist
    await expect(page.getByRole("tab", { name: /applications/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /services/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /members/i })).toBeVisible();
  });

  test("apps tab shows empty state", async ({ page }) => {
    await ensureLoggedIn(page);
    await page.goto(`/tenants/${TENANT_SLUG}`);
    await page.waitForLoadState("networkidle");

    await expect(page.getByText(/no applications yet/i)).toBeVisible();
    await expect(page.getByText(/deploy your first app/i)).toBeVisible();
  });

  test("tenant list shows new tenant", async ({ page }) => {
    await ensureLoggedIn(page);
    await page.goto("/tenants");
    await page.waitForLoadState("networkidle");

    await expect(page.getByText("PW UI Test")).toBeVisible();
  });
});
