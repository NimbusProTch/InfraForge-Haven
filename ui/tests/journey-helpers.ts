/**
 * Real E2E journey helpers — NO mocks, real cluster.
 */
import { type Page, expect } from "@playwright/test";

// 2026-04-18 rename: cluster endpoints moved from *.46.225.42.2.sslip.io
// to iyziops.com. Override via env vars to target a different cluster.
export const UI = process.env.IYZIOPS_UI_URL ?? "https://iyziops.com";
export const API = process.env.IYZIOPS_API_URL ?? "https://api.iyziops.com/api/v1";
export const KC = process.env.IYZIOPS_KC_URL ?? "https://keycloak.iyziops.com";

// Keycloak test client credentials. ESO+Vault pipe is a follow-up sprint;
// for now the UI deployment uses the same static haven-ui-dev-secret-2026.
const KC_CLIENT_ID = process.env.IYZIOPS_KC_CLIENT_ID ?? "haven-ui";
const KC_CLIENT_SECRET = process.env.IYZIOPS_KC_CLIENT_SECRET ?? "haven-ui-dev-secret-2026";
const KC_USER = process.env.IYZIOPS_KC_USER ?? "testuser";
const KC_PASS = process.env.IYZIOPS_KC_PASS ?? "test123456";

// Unique per test run to avoid conflicts
export const SLUG = `e2e-${Date.now().toString(36)}`;

/**
 * Login via Keycloak and return to dashboard.
 * Reuses cookies if already logged in.
 */
export async function login(page: Page) {
  await page.goto(`${UI}/auth/signin`, { waitUntil: "networkidle" });

  // Check if already logged in (redirected to dashboard)
  if (page.url().includes("/dashboard") || page.url().includes("/tenants")) {
    return;
  }

  // Click Keycloak button — could be "Sign in with Keycloak" or just "Keycloak"
  const signinBtn = page.getByRole("button", { name: /sign in|keycloak/i }).first();
  if (await signinBtn.isVisible().catch(() => false)) {
    await signinBtn.click();
  } else {
    await page.getByText(/Keycloak|Sign in/i).first().click();
  }

  // Wait for either Keycloak redirect or back to dashboard (auto-login from prior session)
  try {
    await page.waitForURL(/keycloak|dashboard|tenants/, { timeout: 15_000 });
  } catch {
    // Already on a valid page
  }

  // If still on Keycloak login form, fill it
  if (page.url().includes("keycloak")) {
    await page.fill("#username", KC_USER);
    await page.fill("#password", KC_PASS);
    await page.click("#kc-login");
    await page.waitForURL(/dashboard|tenants/, { timeout: 20_000 });
  }
}

/**
 * Get API bearer token directly from Keycloak (for direct API calls).
 */
export async function getToken(): Promise<string> {
  const body = new URLSearchParams({
    client_id: KC_CLIENT_ID,
    client_secret: KC_CLIENT_SECRET,
    username: KC_USER,
    password: KC_PASS,
    grant_type: "password",
    scope: "openid",
  });
  const res = await fetch(`${KC}/realms/haven/protocol/openid-connect/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });
  const data = await res.json();
  if (!data.access_token) {
    throw new Error(`Keycloak token fetch failed: ${JSON.stringify(data)}`);
  }
  return data.access_token;
}

/**
 * Direct API call (for setup/teardown, not browser-based).
 */
export async function apiCall(
  method: string,
  path: string,
  body?: unknown
): Promise<{ status: number; data: any }> {
  const token = await getToken();
  const res = await fetch(`${API}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    data = text;
  }
  return { status: res.status, data };
}

/**
 * Wait for a condition to be true, polling at interval.
 */
export async function waitFor(
  fn: () => Promise<boolean>,
  { timeout = 120_000, interval = 5_000 } = {}
) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    if (await fn()) return;
    await new Promise((r) => setTimeout(r, interval));
  }
  throw new Error(`waitFor timed out after ${timeout}ms`);
}

/**
 * Screenshot helper with step name.
 */
export async function screenshot(page: Page, step: string) {
  const safe = step.replace(/[^a-z0-9-]/gi, "-").toLowerCase();
  await page.screenshot({ path: `test-results/journey-${safe}.png` });
}
