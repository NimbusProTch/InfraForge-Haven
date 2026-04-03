import { test, expect } from "@playwright/test";
import { mockSession, mockGet, TENANT, SERVICE_PG, SERVICE_REDIS, BACKUP_LIST } from "./helpers";

test.describe("Backup & Restore", () => {
  test.beforeEach(async ({ page }) => {
    await mockSession(page);
    await mockGet(page, `/tenants/${TENANT.slug}`, TENANT);
    await mockGet(page, `/tenants/${TENANT.slug}/apps`, []);
    await mockGet(page, `/tenants/${TENANT.slug}/services`, [SERVICE_PG, SERVICE_REDIS]);
  });

  test("service list shows DB services", async ({ page }) => {
    await page.goto(`/tenants/${TENANT.slug}`);
    await page.getByText("Services").first().click();
    await expect(page.getByText("app-pg").first()).toBeVisible();
  });

  test("backup API mock returns correct structure", async ({ page }) => {
    await mockGet(page, `/tenants/${TENANT.slug}/services/app-pg/backups`, BACKUP_LIST);

    const response = await page.evaluate(async () => {
      const res = await fetch(
        "http://localhost:8000/api/v1/tenants/gemeente-test/services/app-pg/backups"
      );
      return res.json();
    });

    expect(response.backups).toBeDefined();
    expect(response.backups.length).toBeGreaterThan(0);
    expect(response.backups[0].phase).toBe("Succeeded");
  });

  test("backup trigger API mock works", async ({ page }) => {
    let triggered = false;
    await page.route(`**/api/v1/tenants/${TENANT.slug}/services/app-pg/backup`, (route) => {
      if (route.request().method() === "POST") {
        triggered = true;
        route.fulfill({
          status: 202,
          contentType: "application/json",
          body: JSON.stringify({
            message: "Backup triggered",
            backup_name: "backup-test",
            triggered_at: "2026-04-04T10:00:00Z",
          }),
        });
      } else {
        route.continue();
      }
    });

    await page.goto(`/tenants/${TENANT.slug}`);
    await page.evaluate(async () => {
      await fetch("http://localhost:8000/api/v1/tenants/gemeente-test/services/app-pg/backup", {
        method: "POST",
      });
    });
    expect(triggered).toBe(true);
  });
});
