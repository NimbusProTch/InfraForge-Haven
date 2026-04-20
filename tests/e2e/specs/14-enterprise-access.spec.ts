import { test, expect } from "@playwright/test";

/**
 * ET2: enterprise-only funnel — public landing + request-access form.
 *
 * Covers:
 *   - Anonymous landing renders CTAs, no compliance copy leaked
 *   - Sign-in page has the "Request access" link and no stale
 *     "Dutch municipalities" / "Haven 12/15" tagline
 *   - Request-access form submits a 201 to the backend and redirects
 *     to /auth/access-requested
 *
 * Role-gated UI (platform-admin only buttons) is exercised by
 * integration-level tests once the realm role is set up in E2E seed;
 * at this stage we assert the server contract, not the session shape.
 */

test.describe("ET2 — public landing & request-access", () => {
  test("landing page shows enterprise CTAs without compliance copy", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toContainText(
      /ship software with the control your team expects/i
    );
    await expect(page.getByRole("link", { name: /request access/i }).first()).toBeVisible();
    await expect(page.getByRole("link", { name: /sign in/i }).first()).toBeVisible();
    // Must NOT leak the stale "Dutch municipalities" / "Haven 12/15"
    // copy that the login page used to carry. Enterprise-only pivot.
    await expect(page.getByText(/dutch municipalities/i)).toHaveCount(0);
    await expect(page.getByText(/haven 12\/15/i)).toHaveCount(0);
    await expect(page.getByText(/VNG Haven 15\/15 compliant/i)).toHaveCount(0);
  });

  test("sign-in page links to request-access and has no compliance tagline", async ({ page }) => {
    await page.goto("/auth/signin");
    await expect(page.getByText(/need an account/i)).toBeVisible();
    await expect(page.getByRole("link", { name: /request access/i })).toHaveAttribute(
      "href",
      "/auth/request-access"
    );
    await expect(page.getByText(/eu-sovereign paas for dutch municipalities/i)).toHaveCount(0);
    await expect(page.getByText(/haven 12\/15 infrastructure/i)).toHaveCount(0);
  });

  test("request-access form reaches the backend and redirects on 201", async ({ page }) => {
    await page.goto("/auth/request-access");
    await expect(page.getByTestId("request-access-form")).toBeVisible();

    const suffix = Date.now();
    await page.getByLabel(/full name/i).fill("E2E Bot");
    await page.getByLabel(/work email/i).fill(`e2e+${suffix}@example.com`);
    await page.getByLabel(/organization/i).fill("E2E Corp");

    const submit = page.getByRole("button", { name: /request access/i });
    const postResp = page.waitForResponse(
      (r) => r.url().includes("/api/v1/access-requests") && r.request().method() === "POST"
    );
    await submit.click();
    const resp = await postResp;
    expect(resp.status()).toBe(201);

    await page.waitForURL(/\/auth\/access-requested/);
    await expect(page.getByRole("heading", { level: 1 })).toContainText(
      /we(’|')ve got your request/i
    );
  });

  test("request-access form surfaces a server validation error", async ({ page }) => {
    await page.goto("/auth/request-access");

    // mailinator.com is in the disposable-email blocklist — backend returns 422.
    await page.getByLabel(/full name/i).fill("Spammer");
    await page.getByLabel(/work email/i).fill("evil@mailinator.com");
    await page.getByLabel(/organization/i).fill("Spam Inc");
    await page.getByRole("button", { name: /request access/i }).click();

    const error = page.getByTestId("request-access-error");
    await expect(error).toBeVisible();
    await expect(error).toContainText(/work email/i);
  });
});
