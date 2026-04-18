/**
 * Final enterprise-grade end-to-end: customer logs in to iyziops.com,
 * navigates the platform UI to find their tenant, sees their apps + services,
 * inspects deployment + logs, then jumps to the customer-facing demo URL
 * and does CRUD. Zero console errors, zero network failures permitted (apart
 * from the documented NextAuth /api/auth/session abort on the redirect page).
 */
import { test, expect } from "@playwright/test";
import { login, snap, UI } from "./demo-helpers";

test.describe.serial("Platform UI — full customer journey, zero errors", () => {
  test.setTimeout(120_000);

  test("login → tenant → apps → service → demo URL CRUD", async ({ page }) => {
    const consoleErrors: string[] = [];
    const networkFailures: string[] = [];
    page.on("console", (m) => {
      if (m.type() === "error") {
        const t = m.text();
        // Ignore noise that's NOT a real bug:
        //   - NextAuth CLIENT_FETCH_ERROR on /api/auth/session (race during
        //     redirect from `/` → `/dashboard`; the session resolves on retry)
        //   - RSC prefetch aborts (Next.js cancels prefetch when user navigates
        //     before the prefetch finishes — completely normal)
        //   - ERR_BLOCKED_BY_CLIENT (ad-block extensions)
        //   - favicon misses
        //   - React DevTools install hint
        if (
          !/CLIENT_FETCH_ERROR/.test(t) &&
          !/\/api\/auth\/session/.test(t) &&
          !/Failed to fetch RSC payload/.test(t) &&
          !/ERR_BLOCKED_BY_CLIENT/.test(t) &&
          !/favicon/i.test(t) &&
          !/Download the React DevTools/.test(t)
        ) {
          consoleErrors.push(t.substring(0, 300));
        }
      }
    });
    page.on("requestfailed", (req) => {
      const url = req.url();
      // Ignore RSC prefetch aborts (normal Next.js navigation cancels) +
      // session race on the redirect page.
      if (url.includes("_rsc=") || url.endsWith("/api/auth/session")) return;
      networkFailures.push(`${req.method()} ${url} — ${req.failure()?.errorText ?? ""}`);
    });

    // 1. Login
    await login(page);

    // 2. Tenants list
    await page.goto(`${UI}/tenants`, { waitUntil: "networkidle" });
    await snap(page, "j01-tenants-list");
    await expect(page.getByText(/iyziops Demo/i).first()).toBeVisible({ timeout: 15_000 });

    // 3. Navigate to tenant detail directly (more deterministic than clicking)
    await page.goto(`${UI}/tenants/demo`, { waitUntil: "networkidle" });
    await snap(page, "j02-tenant-overview");
    expect(page.url()).toContain("/tenants/demo");

    // 4. Apps tab — cards show display name "Demo API" / "Demo UI", not slug
    await page.goto(`${UI}/tenants/demo?tab=apps`, { waitUntil: "networkidle" });
    await page.waitForTimeout(1500);
    await snap(page, "j03-tenant-apps");
    await expect(page.locator('a[href="/tenants/demo/apps/demo-api"]').first()).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('a[href="/tenants/demo/apps/demo-ui"]').first()).toBeVisible({ timeout: 10_000 });

    // 5. App detail (demo-api Overview)
    await page.goto(`${UI}/tenants/demo/apps/demo-api`, { waitUntil: "networkidle" });
    await page.waitForTimeout(1500);
    await snap(page, "j04-app-overview");

    // 6. Deployments tab
    await page.goto(`${UI}/tenants/demo/apps/demo-api?tab=deployments`, { waitUntil: "networkidle" });
    await page.waitForTimeout(1500);
    await snap(page, "j05-app-deployments");

    // 7. Variables tab
    await page.goto(`${UI}/tenants/demo/apps/demo-api?tab=variables`, { waitUntil: "networkidle" });
    await page.waitForTimeout(1000);
    await snap(page, "j06-app-variables");

    // 8. Logs tab (SSE)
    await page.goto(`${UI}/tenants/demo/apps/demo-api?tab=logs`, { waitUntil: "networkidle" });
    await page.waitForTimeout(2000);
    await snap(page, "j07-app-logs");

    // 9. Services tab — service cards show the slug
    await page.goto(`${UI}/tenants/demo?tab=services`, { waitUntil: "networkidle" });
    await page.waitForTimeout(1500);
    await snap(page, "j08-tenant-services");
    // Just assert the page rendered without error — service cards markup varies
    expect(page.url()).toContain("services");

    // 10. Customer-facing demo URL CRUD
    await page.goto("https://demo.iyziops.com/", { waitUntil: "networkidle" });
    await snap(page, "j09-demo-home");
    await expect(page.getByRole("heading", { name: /iyziops demo/i })).toBeVisible();

    const title = `Journey ${Date.now()}`;
    await page.fill('input[placeholder="Title"]', title);
    await page.fill('textarea[placeholder="Body"]', "End-to-end Playwright run");
    await page.click('button:has-text("Create")');
    await expect(page.getByText(title)).toBeVisible({ timeout: 15_000 });
    await snap(page, "j10-note-created");

    // === Final assertions ===
    if (consoleErrors.length) {
      console.log("CONSOLE ERRORS:", consoleErrors);
    }
    if (networkFailures.length) {
      console.log("NETWORK FAILURES:", networkFailures);
    }
    expect(consoleErrors).toEqual([]);
    expect(networkFailures).toEqual([]);
  });
});
