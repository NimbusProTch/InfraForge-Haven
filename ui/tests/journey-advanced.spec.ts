/**
 * Journey 4: Advanced Features — Orgs, Queue, Scale, Swagger, Health
 * Real cluster, real Keycloak, NO mocks.
 */
import { test, expect } from "@playwright/test";
import { login, UI, SLUG, screenshot, apiCall } from "./journey-helpers";

test.describe.serial("Journey: Advanced Features", () => {
  test.setTimeout(60_000);

  test("V1. Organizations page renders", async ({ page }) => {
    await login(page);
    await page.goto(`${UI}/organizations`);
    await page.waitForLoadState("networkidle");
    await expect(page.getByText(/Organization/i).first()).toBeVisible();
    await screenshot(page, "v1-organizations");
  });

  test("V2. Build Queue page renders", async ({ page }) => {
    await login(page);
    await page.goto(`${UI}/platform/queue`);
    await page.waitForLoadState("networkidle");
    await expect(page.getByText(/Queue|Build|Status/i).first()).toBeVisible();
    await screenshot(page, "v2-queue");
  });

  test("V3. PATCH app replicas via API", async ({ page }) => {
    // Ensure tenant + app exist
    await apiCall("POST", "/tenants", { name: `E2E Journey ${SLUG}`, slug: SLUG });
    await apiCall("POST", `/tenants/${SLUG}/apps`, {
      name: "Journey API", slug: "journey-api",
      repo_url: "https://github.com/NimbusProTch/rotterdam-api",
      branch: "main", port: 8080,
    });

    const { status, data } = await apiCall("PATCH", `/tenants/${SLUG}/apps/journey-api`, {
      replicas: 2,
    });
    expect(status).toBe(200);
    expect(data.replicas).toBe(2);
  });

  test("V4. PATCH env vars via API", async ({ page }) => {
    const { status, data } = await apiCall("PATCH", `/tenants/${SLUG}/apps/journey-api`, {
      env_vars: { TEST_VAR: "hello-e2e" },
    });
    expect(status).toBe(200);
    expect(data.env_vars.TEST_VAR).toBe("hello-e2e");
  });

  test("V5. Swagger docs accessible with endpoints", async ({ page }) => {
    await page.goto("https://api.46.225.42.2.sslip.io/api/docs", { waitUntil: "networkidle" });
    await expect(page.getByText("iyziops")).toBeVisible();
    await expect(page.getByText("tenants").first()).toBeVisible();
    await expect(page.getByText("deployments").first()).toBeVisible();
    await screenshot(page, "v5-swagger");
  });

  test("V6. ReDoc accessible", async ({ page }) => {
    await page.goto("https://api.46.225.42.2.sslip.io/api/redoc", { waitUntil: "networkidle" });
    await expect(page.getByText("iyziops")).toBeVisible();
    await screenshot(page, "v6-redoc");
  });

  test("V7. Health endpoint returns ok", async ({ page }) => {
    const res = await page.goto("https://api.46.225.42.2.sslip.io/health");
    expect(res?.status()).toBe(200);
    const body = await res?.json();
    expect(body.status).toBe("ok");
  });

  test("V8. Readiness endpoint returns ok", async ({ page }) => {
    const res = await page.goto("https://api.46.225.42.2.sslip.io/readiness");
    expect(res?.status()).toBe(200);
  });
});
