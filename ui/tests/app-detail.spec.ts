import { test, expect, type Page } from "@playwright/test";
import { mockSession, mockGet, mockApi, TENANT, APP, DEPLOYMENT, PODS, EVENTS } from "./helpers";

// ---------------------------------------------------------------------------
// Console error collector — fails test if JS errors occur
// ---------------------------------------------------------------------------
function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (err) => errors.push(`[PAGE ERROR] ${err.message}`));
  page.on("console", (msg) => {
    if (msg.type() === "error" && !msg.text().includes("net::ERR_")) {
      errors.push(`[CONSOLE ERROR] ${msg.text()}`);
    }
  });
  return errors;
}

test.describe("App Detail — 6 Tab Enterprise Layout", () => {
  const appPath = `/tenants/${TENANT.slug}/apps/${APP.slug}`;

  test.beforeEach(async ({ page }) => {
    await mockSession(page);
    await mockGet(page, `/tenants/${TENANT.slug}`, TENANT);
    await mockGet(page, `/tenants/${TENANT.slug}/apps/${APP.slug}`, APP);
    await mockGet(page, `/tenants/${TENANT.slug}/apps/${APP.slug}/deployments`, [DEPLOYMENT]);
    await mockGet(page, `/tenants/${TENANT.slug}/apps/${APP.slug}/services`, []);
    await mockGet(page, `/tenants/${TENANT.slug}/apps/${APP.slug}/pods`, PODS);
    await mockGet(page, `/tenants/${TENANT.slug}/apps/${APP.slug}/events`, EVENTS);
    await mockGet(page, `/tenants/${TENANT.slug}/apps/${APP.slug}/build-status`, { containers: [] });
    await page.route(`**/api/v1/tenants/${TENANT.slug}/apps/${APP.slug}/logs**`, (route) =>
      route.fulfill({
        status: 200, contentType: "text/event-stream",
        body: "data: [2026-04-07] App started on port 8080\n\ndata: [2026-04-07] Health check OK\n\ndata: [end]\n\n",
      })
    );
    // Mock PATCH for settings save
    await mockApi(page, `/tenants/${TENANT.slug}/apps/${APP.slug}`, (route) => {
      if (route.request().method() === "PATCH") {
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(APP) });
      } else {
        route.continue();
      }
    });
  });

  // ─── PAGE LOAD & HEADER ───

  test("page loads without console errors", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto(appPath);
    await expect(page.getByText(APP.name).first()).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("header shows app name, status badge, and repo URL", async ({ page }) => {
    await page.goto(appPath);
    await expect(page.getByText(APP.name).first()).toBeVisible();
    await expect(page.getByText("running").first()).toBeVisible();
    // Repo URL without .git suffix, sans-serif font
    await expect(page.getByText("test/repo").first()).toBeVisible();
  });

  test("header shows Build & Deploy primary button", async ({ page }) => {
    await page.goto(appPath);
    const btn = page.getByRole("button", { name: /build.*deploy/i }).first();
    await expect(btn).toBeVisible();
  });

  test("dropdown menu shows Scale, Restart, Deploy options", async ({ page }) => {
    await page.goto(appPath);
    const dropdownTrigger = page.getByRole("button", { name: "More actions" });
    await expect(dropdownTrigger).toBeVisible();
    await dropdownTrigger.click();
    await expect(page.getByRole("menuitem", { name: /scale/i })).toBeVisible();
    await expect(page.getByRole("menuitem", { name: /restart/i })).toBeVisible();
    await expect(page.getByRole("menuitem", { name: /deploy existing/i })).toBeVisible();
  });

  // ─── INFO CARDS ───

  test("3 info cards: Status, Instances, Last Deploy", async ({ page }) => {
    await page.goto(appPath);
    await expect(page.getByText("STATUS").first()).toBeVisible();
    await expect(page.getByText("INSTANCES").first()).toBeVisible();
    await expect(page.getByText("LAST DEPLOY").first()).toBeVisible();
    await expect(page.getByText("2 replicas").first()).toBeVisible();
  });

  // ─── 6 TABS VISIBLE ───

  test("all 6 tabs are visible", async ({ page }) => {
    await page.goto(appPath);
    const tabNames = ["Overview", "Deployments", "Variables", "Logs", "Metrics", "Settings"];
    for (const name of tabNames) {
      await expect(page.getByRole("tab", { name: new RegExp(name, "i") })).toBeVisible();
    }
  });

  // ─── OVERVIEW TAB ───

  test("Overview tab shows latest deployment summary", async ({ page }) => {
    await page.goto(appPath);
    // Default tab is Overview
    await expect(page.getByText(DEPLOYMENT.commit_sha.slice(0, 7)).first()).toBeVisible();
  });

  // ─── DEPLOYMENTS TAB ───

  test("Deployments tab shows full history", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto(appPath);
    await page.getByRole("tab", { name: /deployments/i }).click();
    await expect(page.getByText(DEPLOYMENT.commit_sha.slice(0, 7)).first()).toBeVisible();
    await expect(page.getByText("running").first()).toBeVisible();
    expect(errors).toEqual([]);
    await page.screenshot({ path: "tests/screenshots/deployments-tab.png" });
  });

  // ─── VARIABLES TAB ───

  test("Variables tab shows env var editor", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto(appPath);
    await page.getByRole("tab", { name: /variables/i }).click();
    await expect(page.getByText("Environment Variables").first()).toBeVisible();
    await expect(page.getByRole("button", { name: /save variables/i })).toBeVisible();
    expect(errors).toEqual([]);
    await page.screenshot({ path: "tests/screenshots/variables-tab.png" });
  });

  // ─── LOGS TAB ───

  test("Logs tab shows log terminal and search bar", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto(appPath);
    await page.getByRole("tab", { name: /^logs$/i }).click();
    await expect(page.getByPlaceholder("Filter logs...")).toBeVisible();
    expect(errors).toEqual([]);
    await page.screenshot({ path: "tests/screenshots/logs-tab.png" });
  });

  // ─── METRICS TAB ───

  test("Metrics tab loads without crash", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto(appPath);
    await page.getByRole("tab", { name: /metrics/i }).click();
    // Should show pods or "cluster not reachable" — either is OK, no crash
    await page.waitForTimeout(1000);
    expect(errors).toEqual([]);
    await page.screenshot({ path: "tests/screenshots/metrics-tab.png" });
  });

  // ─── SETTINGS TAB ───

  test("Settings tab shows flat sections (no sub-tabs)", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto(appPath);
    await page.getByRole("tab", { name: /settings/i }).click();
    // Flat sections visible
    await expect(page.getByText("Source & Build").first()).toBeVisible();
    await expect(page.getByText("Networking & Health").first()).toBeVisible();
    await expect(page.getByText("Resources & Scaling").first()).toBeVisible();
    await expect(page.getByText("Danger Zone").first()).toBeVisible();
    // No sub-tabs like "Dependencies" or "Secrets"
    await expect(page.getByRole("tab", { name: /dependencies/i })).not.toBeVisible();
    await expect(page.getByRole("tab", { name: /secrets/i })).not.toBeVisible();
    expect(errors).toEqual([]);
    await page.screenshot({ path: "tests/screenshots/settings-tab.png" });
  });

  test("Settings shows Save Changes button", async ({ page }) => {
    await page.goto(appPath);
    await page.getByRole("tab", { name: /settings/i }).click();
    const saveButtons = page.getByRole("button", { name: /save changes/i });
    await expect(saveButtons.first()).toBeVisible();
  });

  // ─── BUILD MODAL ───

  test("Build & Deploy modal opens and closes", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto(appPath);
    await page.getByRole("button", { name: /build.*deploy/i }).first().click();
    // Modal visible
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.getByText("Build & Deploy").nth(1)).toBeVisible();
    // No static pipeline preview (removed)
    await expect(page.getByText("Build pipeline:")).not.toBeVisible();
    // Close
    await page.getByRole("button", { name: /cancel/i }).click();
    await expect(page.getByRole("dialog")).not.toBeVisible();
    expect(errors).toEqual([]);
  });

  // ─── DEPLOY MODAL ───

  test("Deploy modal opens from dropdown", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto(appPath);
    await page.getByRole("button", { name: "More actions" }).click();
    await page.getByRole("menuitem", { name: /deploy existing/i }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.getByText("Deploy Application")).toBeVisible();
    // Simplified — no CPU/Memory fields
    await expect(page.getByText("CPU LIMIT")).not.toBeVisible();
    await expect(page.getByText("MEMORY LIMIT")).not.toBeVisible();
    // Has instance selector
    await expect(page.getByText("Instances")).toBeVisible();
    expect(errors).toEqual([]);
    await page.screenshot({ path: "tests/screenshots/deploy-modal.png" });
  });

  // ─── FULL SMOKE TEST ───

  test("smoke: navigate all 6 tabs without errors", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto(appPath);

    // Overview (default)
    await page.screenshot({ path: "tests/screenshots/smoke-overview.png" });

    // Deployments
    await page.getByRole("tab", { name: /deployments/i }).click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: "tests/screenshots/smoke-deployments.png" });

    // Variables
    await page.getByRole("tab", { name: /variables/i }).click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: "tests/screenshots/smoke-variables.png" });

    // Logs
    await page.getByRole("tab", { name: /^logs$/i }).click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: "tests/screenshots/smoke-logs.png" });

    // Metrics
    await page.getByRole("tab", { name: /metrics/i }).click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: "tests/screenshots/smoke-metrics.png" });

    // Settings
    await page.getByRole("tab", { name: /settings/i }).click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: "tests/screenshots/smoke-settings.png" });

    // No JS errors through entire navigation
    expect(errors).toEqual([]);
  });
});
