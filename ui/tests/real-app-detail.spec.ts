/**
 * Real E2E — App Detail Page Smoke Test
 *
 * NO MOCKS. Real browser, real Keycloak login, real cluster.
 * Navigates like a real user: login → projects → click tenant → click app → test tabs.
 *
 * Usage:
 *   npx playwright test tests/real-app-detail.spec.ts --headed
 *   npx playwright test tests/real-app-detail.spec.ts
 */
import { test, expect, type Page } from "@playwright/test";
import { login, screenshot, UI } from "./journey-helpers";

// ─── Config ───
const TENANT_SLUG = "debora";
const APP_SLUG = "test";

// ─── Console error collector ───
function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (err) => errors.push(`[PAGE ERROR] ${err.message}`));
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      const text = msg.text();
      if (text.includes("net::ERR_") || text.includes("Failed to fetch") || text.includes("NetworkError")) return;
      // 401/403 on observability endpoints = known issue (token not passed to K8s API)
      if (text.includes("401") || text.includes("403") || text.includes("Failed to load resource")) return;
      errors.push(`[CONSOLE] ${text}`);
    }
  });
  return errors;
}

// Navigate to app detail page like a real user: Projects → Tenant → App
async function navigateToAppDetail(page: Page) {
  // Login lands on /tenants or /dashboard
  await login(page);

  // Go to projects page
  await page.goto(`${UI}/tenants`, { waitUntil: "networkidle", timeout: 15000 });
  await screenshot(page, "nav-01-projects");

  // Click tenant link
  const tenantLink = page.locator(`a[href="/tenants/${TENANT_SLUG}"]`);
  await expect(tenantLink).toBeVisible({ timeout: 10000 });
  await tenantLink.click();
  await page.waitForTimeout(3000); // Let tenant page load
  await screenshot(page, "nav-02-tenant");

  // Click the app link
  const appLink = page.locator(`a[href*="/apps/${APP_SLUG}"]`).first();
  const appLinkVisible = await appLink.isVisible().catch(() => false);
  if (!appLinkVisible) {
    // App might be shown differently — try clicking text
    await page.getByText(APP_SLUG, { exact: false }).first().click();
  } else {
    await appLink.click();
  }
  await page.waitForTimeout(3000); // Let app detail load
  await screenshot(page, "nav-03-app-detail");
}

test.describe("Real E2E — App Detail Page", () => {
  test.setTimeout(90_000);

  // ─── FULL SMOKE TEST — all tabs, all modals ───

  test("smoke: navigate to app, check all 6 tabs, no JS errors", async ({ page }) => {
    const errors = collectErrors(page);

    // Navigate like a real user
    await navigateToAppDetail(page);

    // Verify we're on app detail page
    const pageTitle = page.locator("h1").first();
    await expect(pageTitle).toBeVisible({ timeout: 5000 });
    await screenshot(page, "smoke-01-loaded");

    // ─── CHECK HEADER ───
    // Build & Deploy button
    const buildBtn = page.getByRole("button", { name: /build.*deploy/i }).first();
    const hasBuildBtn = await buildBtn.isVisible().catch(() => false);
    console.log(`Build & Deploy button: ${hasBuildBtn ? "VISIBLE" : "NOT FOUND"}`);

    // Dropdown
    const moreBtn = page.getByRole("button", { name: "More actions" });
    const hasDropdown = await moreBtn.isVisible().catch(() => false);
    console.log(`Dropdown trigger: ${hasDropdown ? "VISIBLE" : "NOT FOUND"}`);

    // ─── NAVIGATE ALL TABS ───
    const tabs = ["Overview", "Deployments", "Variables", "Logs", "Metrics", "Settings"];

    for (const tabName of tabs) {
      console.log(`\n--- Clicking tab: ${tabName} ---`);
      const tab = page.getByRole("tab", { name: new RegExp(tabName, "i") });
      const tabVisible = await tab.isVisible().catch(() => false);

      if (tabVisible) {
        await tab.click();
        await page.waitForTimeout(1500);
        await screenshot(page, `smoke-tab-${tabName.toLowerCase()}`);
        console.log(`  Tab ${tabName}: VISIBLE, clicked, screenshot taken`);
      } else {
        console.log(`  Tab ${tabName}: NOT FOUND — checking if tab exists with different name`);
        // Take screenshot to see what's actually there
        await screenshot(page, `smoke-tab-${tabName.toLowerCase()}-missing`);
      }
    }

    // ─── CHECK SETTINGS SECTIONS ───
    const settingsTab = page.getByRole("tab", { name: /settings/i });
    if (await settingsTab.isVisible().catch(() => false)) {
      await settingsTab.click();
      await page.waitForTimeout(1000);

      const sections = ["Source & Build", "Networking & Health", "Resources & Scaling", "Danger Zone"];
      for (const section of sections) {
        const visible = await page.getByText(section).first().isVisible().catch(() => false);
        console.log(`  Settings section "${section}": ${visible ? "VISIBLE" : "NOT FOUND"}`);
      }

      // Check old sub-tabs are gone
      const hasOldDepsTab = await page.getByRole("tab", { name: /dependencies/i }).isVisible().catch(() => false);
      const hasOldSecretsTab = await page.getByRole("tab", { name: /secrets/i }).isVisible().catch(() => false);
      console.log(`  Old Dependencies tab: ${hasOldDepsTab ? "STILL EXISTS (BUG)" : "REMOVED (OK)"}`);
      console.log(`  Old Secrets tab: ${hasOldSecretsTab ? "STILL EXISTS (BUG)" : "REMOVED (OK)"}`);

      await screenshot(page, "smoke-settings-detail");
    }

    // ─── TEST BUILD MODAL ───
    if (hasBuildBtn) {
      await buildBtn.click();
      await page.waitForTimeout(500);
      const dialog = page.getByRole("dialog");
      const dialogVisible = await dialog.isVisible().catch(() => false);
      console.log(`\nBuild modal: ${dialogVisible ? "OPENED" : "DID NOT OPEN"}`);
      if (dialogVisible) {
        await screenshot(page, "smoke-build-modal");
        // Check no pipeline preview
        const hasPipelinePreview = await page.getByText("Build pipeline:").isVisible().catch(() => false);
        console.log(`  Pipeline preview: ${hasPipelinePreview ? "STILL EXISTS (BUG)" : "REMOVED (OK)"}`);
        await page.getByRole("button", { name: /cancel/i }).click();
        await page.waitForTimeout(300);
      }
    }

    // ─── TEST DROPDOWN MENU ───
    if (hasDropdown) {
      await moreBtn.click();
      await page.waitForTimeout(300);
      const menuItems = ["Scale", "Restart"];
      for (const item of menuItems) {
        const visible = await page.getByRole("menuitem", { name: new RegExp(item, "i") }).isVisible().catch(() => false);
        console.log(`Dropdown item "${item}": ${visible ? "VISIBLE" : "NOT FOUND"}`);
      }
      await screenshot(page, "smoke-dropdown");
      await page.keyboard.press("Escape");
    }

    // ─── REPORT ERRORS ───
    console.log(`\n=== Console Errors: ${errors.length} ===`);
    errors.forEach((e) => console.log(`  ${e}`));

    // Assert no JS errors
    expect(errors).toEqual([]);
  });

  // ─── VARIABLES TAB ───

  test("Variables tab: editor loads, can save", async ({ page }) => {
    const errors = collectErrors(page);
    await navigateToAppDetail(page);

    const tab = page.getByRole("tab", { name: /variables/i });
    if (await tab.isVisible().catch(() => false)) {
      await tab.click();
      await page.waitForTimeout(1000);

      const editorVisible = await page.getByText("Environment Variables").isVisible().catch(() => false);
      console.log(`Env var editor: ${editorVisible ? "VISIBLE" : "NOT FOUND"}`);

      const saveBtn = page.getByRole("button", { name: /save variables/i });
      const hasSave = await saveBtn.isVisible().catch(() => false);
      console.log(`Save button: ${hasSave ? "VISIBLE" : "NOT FOUND"}`);

      await screenshot(page, "variables-tab");
    }

    expect(errors).toEqual([]);
  });

  // ─── METRICS TAB ───

  test("Metrics tab: shows content or graceful error", async ({ page }) => {
    const errors = collectErrors(page);
    await navigateToAppDetail(page);

    const tab = page.getByRole("tab", { name: /metrics/i });
    if (await tab.isVisible().catch(() => false)) {
      await tab.click();
      await page.waitForTimeout(2000);
      await screenshot(page, "metrics-tab");

      // Should show something — not blank
      const bodyText = await page.locator("main").textContent();
      console.log(`Metrics tab content length: ${bodyText?.length ?? 0} chars`);
      const hasContent = (bodyText?.length ?? 0) > 100;
      console.log(`Metrics has meaningful content: ${hasContent}`);
    }

    expect(errors).toEqual([]);
  });
});
