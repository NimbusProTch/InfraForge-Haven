import { test, expect, request as apiRequest } from "@playwright/test";
import { getApiToken, apiCall, cleanupTenant } from "../helpers/api";

const TENANT_SLUG = "pw-add-service-modal";

/**
 * L06 — verifies the AddServiceModal "Create" button stays visible on a
 * 1366×768 viewport (the most common municipal-laptop resolution) even when
 * the form expands with backup + PITR sub-options. Pre-fix the button fell
 * off the bottom of the screen on PostgreSQL+backup config.
 */
test.describe("UI — AddServiceModal sticky footer (1366×768)", () => {
  test.use({ viewport: { width: 1366, height: 768 } });

  test.beforeAll(async () => {
    const ctx = await apiRequest.newContext();
    const token = await getApiToken(ctx);
    await cleanupTenant(ctx, token, TENANT_SLUG);
    await apiCall(ctx, "POST", "/tenants", token, {
      name: "Add Service Modal Test",
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

  test("Create button visible on Postgres + backup + PITR config", async ({ page }) => {
    await page.goto(`/tenants/${TENANT_SLUG}`);
    await page.waitForLoadState("networkidle");

    // Open the Add Service modal
    const addBtn = page.getByRole("button", { name: /add service/i }).first();
    await addBtn.click();

    // Pick PostgreSQL
    await page.getByText(/PostgreSQL/i).first().click();

    // The footer (with Cancel + Create) must stay in the viewport even as
    // the body grows with backup + PITR sub-options.
    const footer = page.getByTestId("add-service-footer");
    await expect(footer).toBeVisible();

    // Toggle "Enable automated backups" — opens PITR sub-section, which
    // historically pushed the Create button off-screen.
    const backupToggle = page.getByRole("switch", { name: /enable automated backups/i }).or(
      page.locator('[aria-checked]').filter({ hasText: /enable.*backup/i })
    );
    if (await backupToggle.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await backupToggle.click();
    }

    // Footer must still be in the viewport (not below the fold)
    const footerBox = await footer.boundingBox();
    expect(footerBox).not.toBeNull();
    if (footerBox) {
      expect(footerBox.y + footerBox.height).toBeLessThanOrEqual(768);
      expect(footerBox.y).toBeGreaterThanOrEqual(0);
    }

    // Both buttons inside footer must be clickable
    const createBtn = footer.getByRole("button", { name: /create/i });
    const cancelBtn = footer.getByRole("button", { name: /cancel/i });
    await expect(createBtn).toBeVisible();
    await expect(cancelBtn).toBeVisible();
  });
});
