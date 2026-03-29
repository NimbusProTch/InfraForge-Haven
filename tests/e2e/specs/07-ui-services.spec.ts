import { test, expect } from "@playwright/test";
import { getApiToken, apiCall, cleanupTenant } from "../helpers/api";

const TENANT_SLUG = "pw-svc-ui";

test.describe("UI — Managed Services", () => {
  test.beforeAll(async ({ request }) => {
    const token = await getApiToken(request);
    await cleanupTenant(request, token, TENANT_SLUG);
    await apiCall(request, "POST", "/tenants", token, {
      name: "Service UI Test",
      slug: TENANT_SLUG,
    });
  });

  test.afterAll(async ({ request }) => {
    const token = await getApiToken(request);
    await cleanupTenant(request, token, TENANT_SLUG);
  });

  test("services tab shows empty state", async ({ page }) => {
    await page.goto(`/tenants/${TENANT_SLUG}`);
    await page.waitForLoadState("networkidle");
    await page.getByRole("tab", { name: /services/i }).click();
    await expect(page.getByText(/no managed services/i)).toBeVisible({ timeout: 5_000 });
  });

  test("add service button exists", async ({ page }) => {
    await page.goto(`/tenants/${TENANT_SLUG}`);
    await page.waitForLoadState("networkidle");
    await page.getByRole("tab", { name: /services/i }).click();
    // "Add Service" button should be visible
    await expect(page.getByRole("button", { name: /add service/i })).toBeVisible({ timeout: 3_000 });
  });
});
