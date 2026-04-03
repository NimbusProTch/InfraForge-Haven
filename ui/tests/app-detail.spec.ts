import { test, expect } from "@playwright/test";
import { mockSession, mockGet, TENANT, APP, DEPLOYMENT, PODS, EVENTS } from "./helpers";

test.describe("App Detail", () => {
  const appPath = `/tenants/${TENANT.slug}/apps/${APP.slug}`;

  test.beforeEach(async ({ page }) => {
    await mockSession(page);
    await mockGet(page, `/tenants/${TENANT.slug}`, TENANT);
    await mockGet(page, `/tenants/${TENANT.slug}/apps/${APP.slug}`, APP);
    await mockGet(page, `/tenants/${TENANT.slug}/apps/${APP.slug}/deployments`, [DEPLOYMENT]);
    await mockGet(page, `/tenants/${TENANT.slug}/apps/${APP.slug}/pods`, PODS);
    await mockGet(page, `/tenants/${TENANT.slug}/apps/${APP.slug}/events`, EVENTS);
    await mockGet(page, `/tenants/${TENANT.slug}/apps/${APP.slug}/sync-status`, {
      sync_status: "Synced", health_status: "Healthy",
    });
    await page.route(`**/api/v1/tenants/${TENANT.slug}/apps/${APP.slug}/logs**`, (route) =>
      route.fulfill({
        status: 200, contentType: "text/event-stream",
        body: "data: App started on port 8080\n\ndata: [end]\n\n",
      })
    );
  });

  test("app detail page renders app name", async ({ page }) => {
    await page.goto(appPath);
    await expect(page.getByText(APP.name).first()).toBeVisible();
  });

  test("shows deployment commit sha", async ({ page }) => {
    await page.goto(appPath);
    await expect(page.getByText(DEPLOYMENT.commit_sha.slice(0, 7)).first()).toBeVisible();
  });

  test("observability tab shows pod name", async ({ page }) => {
    await page.goto(appPath);
    await page.getByText("Observability").first().click();
    await expect(page.getByText("test-api-abc-123").first()).toBeVisible();
  });

  test("deploy button is visible", async ({ page }) => {
    await page.goto(appPath);
    const deployBtn = page.getByRole("button", { name: /deploy|build/i }).first();
    await expect(deployBtn).toBeVisible();
  });
});
