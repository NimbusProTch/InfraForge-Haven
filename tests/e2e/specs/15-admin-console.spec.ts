import { test, expect } from "@playwright/test";

/**
 * ET3: admin console — gated at /admin/*.
 *
 * Non-admin behavior only (happy-path is exercised once ET4 lands the
 * `platform-admin` realm role on testuser). We assert:
 *   - /admin bounces to /auth/signin for anonymous visitors
 *   - /admin renders the "restricted" banner for a signed-in non-admin
 *     (which is the default testuser until ET4 assigns the role).
 *
 * The full admin-review flow is covered by backend integration tests
 * in `api/tests/test_access_requests.py`; the E2E check here is that
 * the UI refuses to surface the feature to users who lack the role.
 */

test.describe("ET3 — admin console role gate", () => {
  test("anonymous visit to /admin redirects to sign-in", async ({ browser }) => {
    // Fresh context — no storage state, so no session.
    const ctx = await browser.newContext({ storageState: undefined });
    const page = await ctx.newPage();
    await page.goto("/admin");
    await page.waitForURL(/\/auth\/signin/);
    await ctx.close();
  });

  test("signed-in non-admin sees the restricted banner", async ({ page }) => {
    // Uses the default authenticated fixture (testuser, no platform-admin
    // role). The layout guard should render admin-forbidden.
    await page.goto("/admin");
    await expect(page.getByTestId("admin-forbidden")).toBeVisible();
    await expect(
      page.getByText(/restricted to platform administrators/i)
    ).toBeVisible();
  });
});
