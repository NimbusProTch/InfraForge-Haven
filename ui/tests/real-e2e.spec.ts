/**
 * REAL E2E Test — No mocks, real cluster, real Keycloak, real UI.
 *
 * This test opens the actual Haven UI at app.46.225.42.2.sslip.io,
 * authenticates via Keycloak, and walks through the full customer journey.
 *
 * Prerequisites:
 *   - Cluster running with UI + API deployed
 *   - Keycloak user: testdev / Test1234!
 *   - Haven realm configured
 */
import { test, expect, type Page } from "@playwright/test";

const UI_URL = "https://app.46.225.42.2.sslip.io";
const API_URL = "https://api.46.225.42.2.sslip.io";
const KC_URL = "https://keycloak.46.225.42.2.sslip.io";

// Helper: get API token directly from Keycloak (bypass UI login for API calls)
async function getApiToken(): Promise<string> {
  const resp = await fetch(
    `${KC_URL}/realms/haven/protocol/openid-connect/token`,
    {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: "client_id=haven-api&username=testdev&password=Test1234!&grant_type=password",
      // @ts-ignore — Node fetch doesn't have this but playwright does
      ...(typeof process !== "undefined" ? {} : {}),
    }
  );
  const data = await resp.json();
  return data.access_token;
}

// Helper: cleanup tenant via API
async function cleanupTenant(slug: string) {
  try {
    const token = await getApiToken();
    await fetch(`${API_URL}/api/v1/tenants/${slug}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    // ignore — tenant may not exist
  }
}

test.describe("Real E2E — Full Customer Journey", () => {
  // Increase timeout for real network calls
  test.setTimeout(120_000);

  test("1. Login page loads with Haven branding", async ({ page }) => {
    await page.goto(`${UI_URL}/auth/signin`, { waitUntil: "networkidle" });

    // Haven branding
    await expect(page.getByText("iyziops")).toBeVisible();

    // Keycloak login button
    await expect(page.getByText(/Keycloak|Sign in/i).first()).toBeVisible();

    // EU compliance text
    await expect(page.getByText(/EU data sovereignty/i)).toBeVisible();

    // Screenshot for proof
    await page.screenshot({ path: "test-results/real-e2e-login.png" });
  });

  test("2. Keycloak login flow works", async ({ page }) => {
    await page.goto(`${UI_URL}/auth/signin`, { waitUntil: "networkidle" });

    // Click Keycloak login button
    await page.getByText(/Keycloak|Sign in with Keycloak/i).first().click();

    // Should redirect to Keycloak login page
    await page.waitForURL(/keycloak.*\/login-actions|keycloak.*\/auth/, { timeout: 15_000 });

    // Fill Keycloak login form
    await page.fill("#username", "testdev");
    await page.fill("#password", "Test1234!");
    await page.click("#kc-login");

    // Should redirect back to dashboard
    await page.waitForURL(/dashboard|tenants/, { timeout: 15_000 });

    // Wait for dashboard content to fully load (not just sidebar)
    await expect(page.getByText("Welcome back").first()).toBeVisible({ timeout: 15_000 });
    // Wait for stat cards to render with actual numbers
    await page.waitForTimeout(3_000);

    await page.screenshot({ path: "test-results/real-e2e-dashboard.png" });
  });

  test("3. Dashboard shows stats after login", async ({ page }) => {
    // Login first
    await page.goto(`${UI_URL}/auth/signin`);
    await page.getByText(/Keycloak|Sign in with Keycloak/i).first().click();
    await page.waitForURL(/keycloak/, { timeout: 10_000 });
    await page.fill("#username", "testdev");
    await page.fill("#password", "Test1234!");
    await page.click("#kc-login");
    await page.waitForURL(/dashboard|tenants/, { timeout: 15_000 });

    // Check stat cards exist
    await expect(page.getByText("Projects", { exact: true }).first()).toBeVisible({ timeout: 10_000 });

    // Quick actions
    await expect(page.getByText("New Project").first()).toBeVisible();
  });

  test("4. Tenant list page renders", async ({ page }) => {
    // Login
    await page.goto(`${UI_URL}/auth/signin`);
    await page.getByText(/Keycloak|Sign in/i).first().click();
    await page.waitForURL(/keycloak/, { timeout: 10_000 });
    await page.fill("#username", "testdev");
    await page.fill("#password", "Test1234!");
    await page.click("#kc-login");
    await page.waitForURL(/dashboard|tenants/, { timeout: 15_000 });

    // Navigate to tenants
    await page.goto(`${UI_URL}/tenants`);
    await page.waitForLoadState("networkidle");

    // Should show existing tenants (rotterdam, amsterdam from earlier tests)
    const content = await page.textContent("body");
    const hasTenants =
      content?.includes("rotterdam") ||
      content?.includes("amsterdam") ||
      content?.includes("No projects") ||
      content?.includes("Create");

    expect(hasTenants).toBeTruthy();

    await page.screenshot({ path: "test-results/real-e2e-tenants.png" });
  });

  test("5. Swagger docs accessible", async ({ page }) => {
    await page.goto(`${API_URL}/api/docs`, { waitUntil: "networkidle" });

    // Swagger UI renders
    await expect(page.getByText("iyziops")).toBeVisible({ timeout: 10_000 });

    // Should show endpoint sections
    await expect(page.getByText("tenants").first()).toBeVisible();

    await page.screenshot({ path: "test-results/real-e2e-swagger.png" });
  });

  test("6. API health endpoint returns ok", async ({ page }) => {
    const response = await page.goto(`${API_URL}/health`);
    expect(response?.status()).toBe(200);

    const body = await response?.json();
    expect(body.status).toBe("ok");
  });

  test("7. Tenant detail page loads with existing data", async ({ page }) => {
    // Login
    await page.goto(`${UI_URL}/auth/signin`);
    await page.getByText(/Keycloak|Sign in/i).first().click();
    await page.waitForURL(/keycloak/, { timeout: 10_000 });
    await page.fill("#username", "testdev");
    await page.fill("#password", "Test1234!");
    await page.click("#kc-login");
    await page.waitForURL(/dashboard|tenants/, { timeout: 15_000 });

    // Navigate to rotterdam tenant (exists from earlier E2E)
    await page.goto(`${UI_URL}/tenants/rotterdam`);
    await page.waitForLoadState("networkidle");

    // Should show tenant name or apps
    const content = await page.textContent("body");
    const loaded =
      content?.includes("rotterdam") ||
      content?.includes("Rotterdam") ||
      content?.includes("Applications");

    expect(loaded).toBeTruthy();

    await page.screenshot({ path: "test-results/real-e2e-tenant-detail.png" });
  });
});
