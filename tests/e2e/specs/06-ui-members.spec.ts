import { test, expect } from "@playwright/test";
import { ensureLoggedIn } from "../helpers/auth";
import { getApiToken, apiCall, cleanupTenant } from "../helpers/api";

const TENANT_SLUG = "pw-member-test";

test.describe("UI — Member Management", () => {
  test.beforeAll(async ({ request }) => {
    const token = await getApiToken(request);
    await cleanupTenant(request, token, TENANT_SLUG);
    await apiCall(request, "POST", "/tenants", token, {
      name: "Member Test",
      slug: TENANT_SLUG,
    });
  });

  test.afterAll(async ({ request }) => {
    const token = await getApiToken(request);
    await cleanupTenant(request, token, TENANT_SLUG);
  });

  test("members tab shows empty state", async ({ page }) => {
    await ensureLoggedIn(page);
    await page.goto(`/tenants/${TENANT_SLUG}`);
    await page.waitForLoadState("networkidle");

    await page.getByRole("tab", { name: /members/i }).click();
    await expect(page.getByText(/no team members/i)).toBeVisible({ timeout: 5_000 });
  });

  test("invite member button opens modal", async ({ page }) => {
    await ensureLoggedIn(page);
    await page.goto(`/tenants/${TENANT_SLUG}`);
    await page.waitForLoadState("networkidle");

    await page.getByRole("tab", { name: /members/i }).click();
    await page.getByRole("button", { name: /invite member/i }).click();

    // Modal should appear
    await expect(page.getByText(/email address/i)).toBeVisible();
    await expect(page.getByText(/display name/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /send invite/i })).toBeVisible();
  });

  test("usage tab loads", async ({ page }) => {
    await ensureLoggedIn(page);
    await page.goto(`/tenants/${TENANT_SLUG}`);
    await page.waitForLoadState("networkidle");

    await page.getByRole("tab", { name: /usage/i }).click();
    // Should show usage data or "not available"
    await expect(
      page.getByText(/resource usage|usage data|cpu|memory/i)
    ).toBeVisible({ timeout: 5_000 });
  });

  test("audit log tab loads", async ({ page }) => {
    await ensureLoggedIn(page);
    await page.goto(`/tenants/${TENANT_SLUG}`);
    await page.waitForLoadState("networkidle");

    await page.getByRole("tab", { name: /audit/i }).click();
    await expect(
      page.getByText(/audit|events|no audit logs/i)
    ).toBeVisible({ timeout: 5_000 });
  });

  test("privacy tab loads", async ({ page }) => {
    await ensureLoggedIn(page);
    await page.goto(`/tenants/${TENANT_SLUG}`);
    await page.waitForLoadState("networkidle");

    await page.getByRole("tab", { name: /privacy/i }).click();
    await expect(page.getByText(/gdpr|data export|retention/i)).toBeVisible({ timeout: 5_000 });
  });
});
