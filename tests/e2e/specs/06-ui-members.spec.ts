import { test, expect } from "@playwright/test";
import { getApiToken, apiCall, cleanupTenant } from "../helpers/api";

const TENANT_SLUG = "pw-member-ui";

test.describe("UI — Tenant Tabs (Members, Usage, Audit, Privacy)", () => {
  test.beforeAll(async ({ request }) => {
    const token = await getApiToken(request);
    await cleanupTenant(request, token, TENANT_SLUG);
    await apiCall(request, "POST", "/tenants", token, {
      name: "Member UI Test",
      slug: TENANT_SLUG,
    });
  });

  test.afterAll(async ({ request }) => {
    const token = await getApiToken(request);
    await cleanupTenant(request, token, TENANT_SLUG);
  });

  test("members tab shows empty state", async ({ page }) => {
    await page.goto(`/tenants/${TENANT_SLUG}`);
    await page.waitForLoadState("networkidle");
    await page.getByRole("tab", { name: /members/i }).click();
    await expect(page.getByText(/no team members/i)).toBeVisible({ timeout: 5_000 });
  });

  test("invite member modal opens", async ({ page }) => {
    await page.goto(`/tenants/${TENANT_SLUG}`);
    await page.waitForLoadState("networkidle");
    await page.getByRole("tab", { name: /members/i }).click();
    await page.getByRole("button", { name: /invite/i }).click();
    await expect(page.getByText(/email address/i)).toBeVisible({ timeout: 3_000 });
    await expect(page.getByRole("button", { name: /send invite/i })).toBeVisible();
  });

  test("usage tab renders", async ({ page }) => {
    await page.goto(`/tenants/${TENANT_SLUG}`);
    await page.waitForLoadState("networkidle");
    await page.getByRole("tab", { name: /usage/i }).click();
    await page.waitForTimeout(2000);
    // Should show usage content or "not available"
    const body = await page.locator("body").textContent();
    expect(body).not.toContain("Application error");
  });

  test("audit log tab renders", async ({ page }) => {
    await page.goto(`/tenants/${TENANT_SLUG}`);
    await page.waitForLoadState("networkidle");
    await page.getByRole("tab", { name: /audit/i }).click();
    await page.waitForTimeout(2000);
    const body = await page.locator("body").textContent();
    expect(body).not.toContain("Application error");
  });

  test("privacy tab renders with GDPR sections", async ({ page }) => {
    await page.goto(`/tenants/${TENANT_SLUG}`);
    await page.waitForLoadState("networkidle");
    await page.getByRole("tab", { name: /privacy/i }).click();
    await expect(page.getByText(/data export/i).first()).toBeVisible({ timeout: 5_000 });
  });
});
