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

  test("root shows public landing for anonymous", async ({ page }) => {
    // ET2: unauthenticated users see the marketing landing at /, not a
    // redirect to /auth/signin. The page must surface both CTAs. Authed
    // users get server-side redirected to /dashboard via getServerSession.
    await page.goto("/");
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("link", { name: /request access/i }).first()).toBeVisible();
    await expect(page.getByRole("link", { name: /sign in/i }).first()).toBeVisible();
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
