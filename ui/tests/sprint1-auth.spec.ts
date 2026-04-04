/**
 * Sprint 1: Auth & Login — Real Browser E2E Tests
 *
 * NO mocks. Real cluster (app.46.225.42.2.sslip.io).
 * Real Keycloak login (testdev / Test1234!).
 * Screenshots at every step.
 */
import { test, expect } from "@playwright/test";

const UI = "https://app.46.225.42.2.sslip.io";
const API = "https://api.46.225.42.2.sslip.io";

// Helper: Keycloak login
async function keycloakLogin(page: import("@playwright/test").Page) {
  await page.goto(`${UI}/auth/signin`, { waitUntil: "networkidle" });
  await page.getByText(/SSO|Keycloak|Sign in/i).first().click();
  await page.waitForURL(/keycloak/, { timeout: 10_000 });
  await page.fill("#username", "testdev");
  await page.fill("#password", "Test1234!");
  await page.click("#kc-login");
  await page.waitForURL(/dashboard|tenants/, { timeout: 15_000 });
}

test.describe.serial("Sprint 1: Auth & Login", () => {
  test.setTimeout(60_000);

  test("P01. Login page — enterprise branding", async ({ page }) => {
    await page.goto(`${UI}/auth/signin`, { waitUntil: "networkidle" });

    // Haven branding
    await expect(page.getByText("Haven Platform")).toBeVisible();

    // EU-Sovereign subtitle
    await expect(page.getByText(/EU-Sovereign|municipalities/i)).toBeVisible();

    // SSO button (primary action)
    await expect(page.getByText(/Sign in with SSO/i)).toBeVisible();

    // Compliance footer
    await expect(page.getByText(/EU Data Sovereignty/i)).toBeVisible();
    await expect(page.getByText(/VNG Haven/i)).toBeVisible();

    // Forgot password link
    await expect(page.getByText(/Forgot password/i)).toBeVisible();

    await page.screenshot({ path: "test-results/sprint1/p01-login-page.png" });
  });

  test("P02. Keycloak login → dashboard redirect", async ({ page }) => {
    await page.goto(`${UI}/auth/signin`, { waitUntil: "networkidle" });

    // Click SSO button
    await page.getByText(/SSO|Keycloak/i).first().click();

    // Keycloak form renders
    await page.waitForURL(/keycloak/, { timeout: 10_000 });
    await expect(page.locator("#username")).toBeVisible();
    await expect(page.locator("#password")).toBeVisible();
    await page.screenshot({ path: "test-results/sprint1/p02-keycloak-form.png" });

    // Fill and submit
    await page.fill("#username", "testdev");
    await page.fill("#password", "Test1234!");
    await page.click("#kc-login");

    // Dashboard redirect
    await page.waitForURL(/dashboard/, { timeout: 15_000 });
    await page.screenshot({ path: "test-results/sprint1/p02-after-login.png" });
  });

  test("P03. Dashboard shows real data", async ({ page }) => {
    await keycloakLogin(page);

    // Wait for actual content (not just sidebar)
    await expect(page.getByText("Welcome back")).toBeVisible({ timeout: 15_000 });

    // Stat cards with data
    await page.waitForTimeout(3_000);
    await page.screenshot({ path: "test-results/sprint1/p03-dashboard-data.png" });
  });

  test("P04. Sidebar navigation complete", async ({ page }) => {
    await keycloakLogin(page);
    await page.waitForTimeout(2_000);

    // Platform section
    await expect(page.getByText("Platform", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Dashboard").first()).toBeVisible();
    await expect(page.getByText("Projects").first()).toBeVisible();
    await expect(page.getByText("Organizations").first()).toBeVisible();

    // Operations section
    await expect(page.getByText("Operations", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Build Queue").first()).toBeVisible();

    await page.screenshot({ path: "test-results/sprint1/p04-sidebar.png" });
  });

  test("P05. User info in sidebar", async ({ page }) => {
    await keycloakLogin(page);
    await page.waitForTimeout(2_000);

    // User email or name visible
    const userInfo = page.getByText(/test@haven|testdev/i).first();
    await expect(userInfo).toBeVisible();

    await page.screenshot({ path: "test-results/sprint1/p05-user-info.png" });
  });

  test("P06. Logout redirects to signin", async ({ page }) => {
    await keycloakLogin(page);
    await page.waitForTimeout(2_000);

    // Find and click logout
    const logoutBtn = page.locator("[title='Sign out']").or(
      page.getByRole("button", { name: /sign out|logout/i })
    );
    await logoutBtn.first().click();

    // Should redirect to signin
    await page.waitForURL(/signin/, { timeout: 10_000 });
    await expect(page.getByText("Haven Platform")).toBeVisible();

    await page.screenshot({ path: "test-results/sprint1/p06-logged-out.png" });
  });

  test("P07. Protected route redirects to signin (middleware)", async ({ page }) => {
    // Go directly to protected route WITHOUT login
    const resp = await page.goto(`${UI}/tenants`, { waitUntil: "networkidle" });

    // Should be redirected to signin page by middleware
    await page.waitForURL(/signin|auth/, { timeout: 10_000 });

    await page.screenshot({ path: "test-results/sprint1/p07-middleware-redirect.png" });
  });

  test("P08. Forgot password link visible on Keycloak", async ({ page }) => {
    await page.goto(`${UI}/auth/signin`, { waitUntil: "networkidle" });
    await page.getByText(/SSO|Keycloak/i).first().click();
    await page.waitForURL(/keycloak/, { timeout: 10_000 });

    // Keycloak should have reset password link
    const resetLink = page.getByText(/Forgot|Reset/i);
    await expect(resetLink.first()).toBeVisible();

    await page.screenshot({ path: "test-results/sprint1/p08-forgot-password.png" });
  });

  test("P09. API health endpoint returns ok", async ({ page }) => {
    const resp = await page.goto(`${API}/health`);
    expect(resp?.status()).toBe(200);
    const body = await resp?.json();
    expect(body.status).toBe("ok");
  });

  test("P10. Swagger docs accessible", async ({ page }) => {
    await page.goto(`${API}/api/docs`, { waitUntil: "networkidle" });
    await expect(page.getByText("Haven Platform API")).toBeVisible({ timeout: 10_000 });
    await page.screenshot({ path: "test-results/sprint1/p10-swagger.png" });
  });
});
