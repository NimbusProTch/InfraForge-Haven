/**
 * Shared helpers for demo-* Playwright specs.
 * These tests hit LIVE https://iyziops.com — no local server.
 */
import { type Page, expect } from "@playwright/test";

export const UI = "https://iyziops.com";
export const API = "https://api.iyziops.com";
export const KC = "https://keycloak.iyziops.com";
export const TENANT_SLUG = "demo";
export const DEMO_USER = "testuser";
export const DEMO_PASS = "test123456";

/** Login via Keycloak. Reuses session if already signed in. */
export async function login(page: Page) {
  await page.goto(`${UI}/`, { waitUntil: "networkidle" });
  // If already at dashboard/tenants/organizations, skip
  if (/\/(dashboard|organizations|tenants|platform)/.test(page.url())) {
    return;
  }
  // Else go to signin
  if (!page.url().includes("/auth/signin")) {
    await page.goto(`${UI}/auth/signin`, { waitUntil: "networkidle" });
  }
  const kcBtn = page.getByRole("button", { name: /keycloak|sign in/i }).first();
  await kcBtn.click({ timeout: 10_000 }).catch(() => {});
  await page.waitForURL(/keycloak\.iyziops\.com|iyziops\.com\/(dashboard|organizations|tenants)/, { timeout: 15_000 }).catch(() => {});
  if (page.url().includes("keycloak")) {
    await page.fill("#username", DEMO_USER);
    await page.fill("#password", DEMO_PASS);
    await page.click("#kc-login");
    await page.waitForURL(/iyziops\.com\/(dashboard|organizations|tenants)/, { timeout: 20_000 });
  }
}

/** Get Keycloak access token for direct API calls. */
export async function getToken(): Promise<string> {
  const body = new URLSearchParams({
    client_id: "haven-ui",
    client_secret: "haven-ui-dev-secret-2026",
    username: DEMO_USER,
    password: DEMO_PASS,
    grant_type: "password",
    scope: "openid",
  });
  const res = await fetch(`${KC}/realms/haven/protocol/openid-connect/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });
  const data = await res.json();
  if (!data.access_token) throw new Error(`Keycloak token failed: ${JSON.stringify(data)}`);
  return data.access_token;
}

/** Simple API wrapper for setup/teardown (uses direct token, not through UI). */
export async function apiCall<T = any>(
  method: string,
  path: string,
  body?: unknown
): Promise<{ status: number; data: T }> {
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
  let data: any;
  try {
    data = JSON.parse(text);
  } catch {
    data = text;
  }
  return { status: res.status, data };
}

/** Wait until predicate is truthy, poll at interval, timeout in ms. */
export async function waitFor(
  predicate: () => Promise<boolean>,
  opts: { timeout?: number; interval?: number; label?: string } = {}
): Promise<void> {
  const { timeout = 300_000, interval = 5_000, label = "condition" } = opts;
  const start = Date.now();
  while (Date.now() - start < timeout) {
    if (await predicate()) return;
    await new Promise((r) => setTimeout(r, interval));
  }
  throw new Error(`Timed out after ${timeout}ms waiting for ${label}`);
}

/** Take a screenshot named by step. */
export async function snap(page: Page, step: string) {
  const safe = step.replace(/[^a-z0-9-]/gi, "-").toLowerCase();
  await page.screenshot({ path: `playwright-report-demo/screens/${safe}.png`, fullPage: true });
}
