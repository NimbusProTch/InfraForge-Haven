import { test, expect } from "@playwright/test";
import { ensureLoggedIn } from "../helpers/auth";
import { getApiToken, apiCall, cleanupTenant } from "../helpers/api";

const TENANT_SLUG = "pw-svc-test";

test.describe("UI — Managed Services", () => {
  test.beforeAll(async ({ request }) => {
    const token = await getApiToken(request);
    await cleanupTenant(request, token, TENANT_SLUG);
    await apiCall(request, "POST", "/tenants", token, {
      name: "Service Test",
      slug: TENANT_SLUG,
    });
  });

  test.afterAll(async ({ request }) => {
    const token = await getApiToken(request);
    await cleanupTenant(request, token, TENANT_SLUG);
  });

  test("services tab shows empty state", async ({ page }) => {
    await ensureLoggedIn(page);
    await page.goto(`/tenants/${TENANT_SLUG}`);
    await page.waitForLoadState("networkidle");

    await page.getByRole("tab", { name: /services/i }).click();
    await expect(page.getByText(/no managed services/i)).toBeVisible({ timeout: 5_000 });
  });

  test("add service button opens modal", async ({ page }) => {
    await ensureLoggedIn(page);
    await page.goto(`/tenants/${TENANT_SLUG}`);
    await page.waitForLoadState("networkidle");

    await page.getByRole("tab", { name: /services/i }).click();
    await page.getByRole("button", { name: /add service/i }).click();

    // Modal should show service types
    await expect(page.getByText(/postgresql|redis|rabbitmq/i)).toBeVisible();
  });
});
