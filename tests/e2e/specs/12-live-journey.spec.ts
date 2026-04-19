/**
 * Live cluster journey with screenshots — run against https://iyziops.com.
 * Captures visual state BEFORE + AFTER the L02–L12 PR series deploys so
 * the operator can eyeball each feature.
 */
import { test, expect } from "@playwright/test";
import path from "node:path";

const SCREEN_DIR = path.join(__dirname, "..", "..", "..", "docs", "demo", "longsprint-20260419");

test.use({ viewport: { width: 1440, height: 900 } });
test.describe("Live production journey", () => {

  test("A. Sign-in page", async ({ browser }) => {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await page.goto("/auth/signin");
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: `${SCREEN_DIR}/A-signin.png`, fullPage: true });
    await ctx.close();
  });

  test("B. Dashboard (authenticated)", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${SCREEN_DIR}/B-dashboard.png`, fullPage: true });
  });

  test("C. Tenants list", async ({ page }) => {
    await page.goto("/tenants");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${SCREEN_DIR}/C-tenants.png`, fullPage: true });
  });

  test("D. Demo tenant detail — services + apps", async ({ page }) => {
    await page.goto("/tenants/demo");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2000);
    await page.screenshot({ path: `${SCREEN_DIR}/D-demo-tenant.png`, fullPage: true });
  });

  test("E. Demo app detail", async ({ page }) => {
    await page.goto("/tenants/demo/apps/demo-api");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(3000);
    await page.screenshot({ path: `${SCREEN_DIR}/E-demo-app-detail.png`, fullPage: true });
  });

  test("F. Demo app — Observability tab", async ({ page }) => {
    await page.goto("/tenants/demo/apps/demo-api");
    await page.waitForLoadState("networkidle");
    const obsTab = page.getByRole("tab", { name: /observability/i });
    if (await obsTab.isVisible({ timeout: 3000 }).catch(() => false)) {
      await obsTab.click();
      await page.waitForTimeout(6000);  // let metrics poll land
      await page.screenshot({ path: `${SCREEN_DIR}/F-observability.png`, fullPage: true });
    }
  });

  test("G. New app wizard — step 2 source", async ({ page }) => {
    await page.goto("/tenants/demo/apps/new");
    await page.waitForLoadState("networkidle");
    const nameInput = page.locator('input[placeholder*="My App"]');
    if (await nameInput.isVisible({ timeout: 3000 }).catch(() => false)) {
      await nameInput.fill("journey-smoke");
      await page.getByRole("button", { name: /continue/i }).first().click();
      await page.waitForTimeout(1500);
    }
    await page.screenshot({ path: `${SCREEN_DIR}/G-new-app-source.png`, fullPage: true });
  });

  test("H. Add Service modal on Postgres + backup toggle", async ({ page }) => {
    await page.goto("/tenants/demo");
    await page.waitForLoadState("networkidle");
    const addBtn = page.getByRole("button", { name: /add service/i }).first();
    if (!(await addBtn.isVisible({ timeout: 3000 }).catch(() => false))) {
      test.skip(true, "Add Service not present");
    }
    await addBtn.click();
    await page.waitForTimeout(500);
    const pgCard = page.getByText(/PostgreSQL/i).first();
    if (await pgCard.isVisible({ timeout: 3000 }).catch(() => false)) {
      await pgCard.click();
      await page.waitForTimeout(800);
      // Toggle backup if visible
      const backupToggle = page.locator('[aria-checked]').first();
      if (await backupToggle.isVisible({ timeout: 2000 }).catch(() => false)) {
        await backupToggle.click().catch(() => {});
        await page.waitForTimeout(500);
      }
    }
    await page.screenshot({ path: `${SCREEN_DIR}/H-add-service-modal.png`, fullPage: true });
  });
});
