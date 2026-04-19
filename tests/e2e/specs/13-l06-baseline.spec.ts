import { test, expect } from "@playwright/test";
import path from "node:path";

test.use({ viewport: { width: 1366, height: 768 } });

test("L06 baseline at 1366x768", async ({ page }) => {
  await page.goto("/tenants/demo");
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(2000);
  const addBtn = page.getByRole("button", { name: /add service/i }).first();
  if (!(await addBtn.isVisible({ timeout: 3000 }).catch(() => false))) {
    test.skip(true, "no add service button");
  }
  await addBtn.click();
  await page.waitForTimeout(500);
  const pg = page.getByText(/PostgreSQL/i).first();
  if (await pg.isVisible({ timeout: 3000 }).catch(() => false)) {
    await pg.click();
    await page.waitForTimeout(800);
    // toggle backup
    const toggle = page.locator('[aria-checked]').first();
    if (await toggle.isVisible({ timeout: 2000 }).catch(() => false)) {
      await toggle.click().catch(() => {});
    }
    await page.waitForTimeout(500);
  }
  await page.screenshot({
    path: path.join(__dirname, "..", "..", "..", "docs", "demo", "longsprint-20260419", "L06-baseline-1366x768.png"),
    fullPage: false, // clip to viewport so the bug is visible
  });
});
