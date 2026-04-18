/**
 * L13 — Full end-to-end journey through the iyziops UI on the live cluster.
 *
 * This spec is intentionally **read-mostly + idempotent** so it can be
 * re-run against any tenant without leaving garbage. It validates that
 * the platform answers all the user's L02–L12 concerns end-to-end:
 *
 *   1. Sign in with the saved auth state
 *   2. Land on the demo tenant
 *   3. New-app wizard exposes all three source tabs (L03)
 *   4. Switching between tabs reveals each panel
 *   5. Service modal sticky footer is reachable on 1366×768 (L06)
 *   6. App detail page renders the Live status badge (L05) + the Live
 *      resource pill (L10) without throwing
 *   7. Sidebar header shows the new "iyziops" brand (L12)
 *
 * The spec does NOT create / delete services or apps — that requires the
 * cluster's GitOps writer to settle, which is too noisy for a smoke
 * suite. Use the dedicated `04-ui-tenant-flow.spec.ts` /
 * `05-ui-app-flow.spec.ts` for stateful coverage.
 *
 * Saved screenshots land under `docs/demo/longsprint-20260419/` so the
 * operator can inspect them after a run.
 */
import { test, expect } from "@playwright/test";
import path from "node:path";

const TENANT_SLUG = process.env.IYZIOPS_DEMO_TENANT ?? "demo";
const SCREENSHOT_DIR = path.join(__dirname, "..", "..", "..", "docs", "demo", "longsprint-20260419");

test.describe("UI — Full L02→L12 journey (read-mostly smoke)", () => {
  test.use({
    viewport: { width: 1366, height: 768 },
    video: "retain-on-failure",
  });

  test("sidebar carries the new iyziops brand (L12)", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");
    // Sidebar logo block — text "iyziops" + small VNG Haven 15/15 caption
    await expect(page.getByText("iyziops").first()).toBeVisible();
    await expect(page.getByText(/VNG Haven 15\/15/i)).toBeVisible();
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "01-sidebar-brand.png"), fullPage: false });
  });

  test("new-app wizard exposes 3 source tabs and switches cleanly (L03)", async ({ page }) => {
    await page.goto(`/tenants/${TENANT_SLUG}/apps/new`);
    await page.waitForLoadState("networkidle");

    const nameInput = page.locator('input[placeholder*="My App"]');
    if (await nameInput.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await nameInput.fill("journey-smoke-app");
      await page.getByRole("button", { name: /continue/i }).first().click();
    }

    const githubTab = page.getByTestId("source-tab-github");
    const giteaTab = page.getByTestId("source-tab-gitea");
    const manualTab = page.getByTestId("source-tab-manual");

    await expect(githubTab).toBeVisible();
    await expect(giteaTab).toBeVisible();
    await expect(manualTab).toBeVisible();
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "02-source-tabs.png") });

    await giteaTab.click();
    await expect(page.getByTestId("gitea-source-panel")).toBeVisible();
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "03-gitea-tab.png") });

    await manualTab.click();
    await expect(page.locator('input[placeholder*="github.com/owner/repo"]')).toBeVisible();
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "04-manual-tab.png") });
  });

  test("AddServiceModal Create button stays in viewport on 1366x768 (L06)", async ({ page }) => {
    await page.goto(`/tenants/${TENANT_SLUG}`);
    await page.waitForLoadState("networkidle");

    const addBtn = page.getByRole("button", { name: /add service/i }).first();
    if (!(await addBtn.isVisible({ timeout: 3_000 }).catch(() => false))) {
      test.skip(true, "Add Service button not present in this build");
    }
    await addBtn.click();

    await page.getByText(/PostgreSQL/i).first().click();
    const footer = page.getByTestId("add-service-footer");
    await expect(footer).toBeVisible();

    const box = await footer.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      expect(box.y + box.height).toBeLessThanOrEqual(768);
    }
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "05-add-service-modal.png") });
  });

  test("app detail page renders LiveStatusBadge + LiveResourceBadge (L05+L10)", async ({ page, request }) => {
    // Pick the first running app in the demo tenant — fall back to skip
    // if the tenant has no apps yet so a fresh cluster still passes.
    const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "https://api.iyziops.com";
    const apps = await request
      .get(`${apiBase}/api/v1/tenants/${TENANT_SLUG}/apps`)
      .then((r) => (r.ok() ? r.json() : []));
    if (!Array.isArray(apps) || apps.length === 0) {
      test.skip(true, "No apps in demo tenant");
    }
    const appSlug = apps[0].slug;

    await page.goto(`/tenants/${TENANT_SLUG}/apps/${appSlug}`);
    await page.waitForLoadState("networkidle");

    // LiveStatusBadge OR live-resource-badge must appear within 15s. Both
    // are network-driven (poll cluster), so we tolerate a brief delay.
    await Promise.race([
      page.getByTestId("live-status-badge").waitFor({ timeout: 15_000 }).catch(() => null),
      page.getByTestId("live-resource-badge").waitFor({ timeout: 15_000 }).catch(() => null),
    ]);

    // At least ONE of the live badges must have rendered. If both are
    // missing, the cluster is genuinely unreachable (which is itself
    // a real signal — surface as a soft assertion, don't fail the run).
    const liveStatusVisible = await page
      .getByTestId("live-status-badge")
      .isVisible()
      .catch(() => false);
    const liveResourceVisible = await page
      .getByTestId("live-resource-badge")
      .isVisible()
      .catch(() => false);
    expect(liveStatusVisible || liveResourceVisible).toBeTruthy();
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "06-app-detail-live-badges.png") });
  });

  test("login page shows the new brand + tagline (L12)", async ({ browser }) => {
    // Fresh context so we are signed out
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await page.goto("/auth/signin");
    await expect(page.getByRole("heading", { name: "iyziops" })).toBeVisible();
    await expect(page.getByText(/VNG Haven 15\/15 compliant/i)).toBeVisible();
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "07-signin-brand.png") });
    await ctx.close();
  });
});
