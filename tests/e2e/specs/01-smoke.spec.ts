import { test, expect } from "@playwright/test";

test.describe("Smoke Tests — Pages Load", () => {
  test("login page loads", async ({ page }) => {
    await page.goto("/auth/signin");
    await expect(page.getByText("iyziops")).toBeVisible();
    await expect(page.getByRole("button", { name: /sso|keycloak/i })).toBeVisible();
  });

  test("login page has correct title", async ({ page }) => {
    await page.goto("/auth/signin");
    // After the rename the browser title is "iyziops". Accept either so
    // the spec survives a (temporary) rollback of the rename PR.
    await expect(page).toHaveTitle(/iyziops|Haven/i);
  });

  test("root redirects to dashboard", async ({ page }) => {
    await page.goto("/");
    await page.waitForURL(/\/(dashboard|auth)/);
  });

  test("API health endpoint returns ok", async ({ request }) => {
    const apiUrl = process.env.API_URL || "http://localhost:8000";
    const resp = await request.get(`${apiUrl}/health`);
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body.status).toBe("ok");
  });

  test("API readiness endpoint returns ready", async ({ request }) => {
    const apiUrl = process.env.API_URL || "http://localhost:8000";
    const resp = await request.get(`${apiUrl}/readiness`);
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body.status).toBe("ready");
    expect(body.checks.database).toBe("ok");
  });
});
