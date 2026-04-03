import { test, expect } from "@playwright/test";
import { mockSession, mockGet, TENANT, MEMBER } from "./helpers";

test.describe("Team Members", () => {
  test.beforeEach(async ({ page }) => {
    await mockSession(page);
    await mockGet(page, `/tenants/${TENANT.slug}`, TENANT);
    await mockGet(page, `/tenants/${TENANT.slug}/apps`, []);
    await mockGet(page, `/tenants/${TENANT.slug}/services`, []);
    await mockGet(page, `/tenants/${TENANT.slug}/members`, [MEMBER]);
  });

  test("members tab renders member email", async ({ page }) => {
    await page.goto(`/tenants/${TENANT.slug}`);
    await page.getByText("Members").first().click();
    await expect(page.getByText(MEMBER.email).first()).toBeVisible();
  });

  test("invite button exists", async ({ page }) => {
    await page.goto(`/tenants/${TENANT.slug}`);
    await page.getByText("Members").first().click();
    await expect(
      page.getByRole("button", { name: /invite|add/i }).first()
    ).toBeVisible();
  });

  test("empty members tab renders", async ({ page }) => {
    await mockGet(page, `/tenants/${TENANT.slug}/members`, []);
    await page.goto(`/tenants/${TENANT.slug}`);
    await page.getByText("Members").first().click();
    // Should render the tab without errors
    await expect(page.getByText("Members").first()).toBeVisible();
  });
});
