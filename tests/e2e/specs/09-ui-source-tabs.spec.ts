import { test, expect, request as apiRequest } from "@playwright/test";
import { getApiToken, apiCall, cleanupTenant } from "../helpers/api";

const TENANT_SLUG = "pw-source-tabs";

/**
 * L03 — verifies the new 3-way source picker (GitHub / Gitea / Manual URL) on
 * /tenants/<slug>/apps/new. Each tab must be selectable and reveal its own
 * panel without throwing.
 */
test.describe("UI — App-create Source picker (GitHub / Gitea / Manual)", () => {
  test.beforeAll(async () => {
    const ctx = await apiRequest.newContext();
    const token = await getApiToken(ctx);
    await cleanupTenant(ctx, token, TENANT_SLUG);
    await apiCall(ctx, "POST", "/tenants", token, {
      name: "Source Tabs Test",
      slug: TENANT_SLUG,
    });
    await ctx.dispose();
  });

  test.afterAll(async () => {
    const ctx = await apiRequest.newContext();
    const token = await getApiToken(ctx);
    await cleanupTenant(ctx, token, TENANT_SLUG);
    await ctx.dispose();
  });

  test("source picker shows three tabs and switches panels cleanly", async ({ page }) => {
    await page.goto(`/tenants/${TENANT_SLUG}/apps/new`);
    await page.waitForLoadState("networkidle");

    // Step 1 only asks for app identity — fill the bare minimum and Continue
    const nameInput = page.locator('input[placeholder*="My App"]');
    if (await nameInput.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await nameInput.fill("source-tab-test");
      // Click Continue to advance to step 2
      await page.getByRole("button", { name: /continue/i }).first().click();
    }

    // Now on Step 2 — source picker must be visible
    const githubTab = page.getByTestId("source-tab-github");
    const giteaTab = page.getByTestId("source-tab-gitea");
    const manualTab = page.getByTestId("source-tab-manual");

    await expect(githubTab).toBeVisible({ timeout: 5_000 });
    await expect(giteaTab).toBeVisible();
    await expect(manualTab).toBeVisible();

    // Default selection is GitHub
    await expect(githubTab).toHaveAttribute("aria-selected", "true");

    // Switch to Gitea — panel renders without throwing
    await giteaTab.click();
    await expect(giteaTab).toHaveAttribute("aria-selected", "true");
    await expect(page.getByTestId("gitea-source-panel")).toBeVisible();

    // Switch to Manual URL — input is shown
    await manualTab.click();
    await expect(manualTab).toHaveAttribute("aria-selected", "true");
    await expect(page.locator('input[placeholder*="github.com/owner/repo"]')).toBeVisible();

    // Back to GitHub — Connect-GitHub button (or already-connected card) must appear
    await githubTab.click();
    await expect(githubTab).toHaveAttribute("aria-selected", "true");
  });
});
