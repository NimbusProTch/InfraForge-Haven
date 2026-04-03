import { test, expect } from "@playwright/test";
import { mockSession, mockGet, TENANT, APP, DEPLOYMENT, PODS, EVENTS } from "./helpers";

test.describe("Observability", () => {
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
        body: "data: App listening on port 8080\n\ndata: [end]\n\n",
      })
    );
  });

  test("pods section shows pod name", async ({ page }) => {
    await page.goto(appPath);
    await page.getByText("Observability").first().click();
    await expect(page.getByText("test-api-abc-123").first()).toBeVisible();
  });

  test("pod CPU metric is displayed", async ({ page }) => {
    await page.goto(appPath);
    await page.getByText("Observability").first().click();
    await expect(page.getByText("CPU").first()).toBeVisible();
  });

  test("k8s unavailable shows cluster unavailable", async ({ page }) => {
    await mockGet(page, `/tenants/${TENANT.slug}/apps/${APP.slug}/pods`, {
      k8s_available: false, pods: [],
    });
    await mockGet(page, `/tenants/${TENANT.slug}/apps/${APP.slug}/events`, {
      k8s_available: false, events: [],
    });

    await page.goto(appPath);
    await page.getByText("Observability").first().click();
    await expect(page.getByText("unavailable").first()).toBeVisible();
  });
});
