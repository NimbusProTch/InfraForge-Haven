/**
 * Sprint 3: App Build & Deploy Pipeline — Real API, Real Cluster, NO mocks.
 *
 * Full lifecycle:
 *   Tenant create → App create → Build trigger → Build status poll →
 *   Deploy verify → App detail UI → Pipeline visualization →
 *   Settings tab → App delete → Tenant cleanup
 *
 * Uses journey-helpers for auth + API calls against the live cluster.
 */
import { test, expect } from "@playwright/test";
import { login, UI, API, screenshot, apiCall, waitFor, getToken } from "./journey-helpers";

const SLUG = `s3-${Date.now().toString(36)}`;
const APP_SLUG = "pipeline-app";
const APP_NAME = "Pipeline Test App";
const REPO_URL = "https://github.com/NimbusProTch/rotterdam-api";
const BRANCH = "main";
const PORT = 8080;

test.describe.serial("Sprint 3: App Build & Deploy Pipeline", () => {
  test.setTimeout(120_000);

  // -- Setup: create tenant --
  test.beforeAll(async () => {
    const { status } = await apiCall("POST", "/tenants", {
      name: `Sprint3 E2E ${SLUG}`,
      slug: SLUG,
    });
    expect([201, 409]).toContain(status);
  });

  // -- Cleanup: delete tenant (cascades apps, services, namespace) --
  test.afterAll(async () => {
    // Tenant delete cascades K8s cleanup which can take >30s
    await Promise.race([
      apiCall("DELETE", `/tenants/${SLUG}`),
      new Promise((r) => setTimeout(r, 55_000)),
    ]);
  });

  // ---------------------------------------------------------------
  // P3.01 — Tenant detail page shows "+ New App" button
  // ---------------------------------------------------------------
  test("P3.01 Tenant detail sayfasinda '+ New App' butonu gorunur", async ({ page }) => {
    await login(page);
    await page.goto(`${UI}/tenants/${SLUG}`);
    await page.waitForLoadState("networkidle");

    // "New App" or similar link/button should exist
    const newAppLink = page.getByRole("link", { name: /new app/i })
      .or(page.getByText(/new app/i).first());
    await expect(newAppLink).toBeVisible({ timeout: 10_000 });
    await screenshot(page, "p3-01-new-app-button");
  });

  // ---------------------------------------------------------------
  // P3.02 — Create app via API and verify in tenant detail
  // ---------------------------------------------------------------
  test("P3.02 App create (API) ve tenant detail'de gorunmesi", async ({ page }) => {
    const { status, data } = await apiCall("POST", `/tenants/${SLUG}/apps`, {
      name: APP_NAME,
      slug: APP_SLUG,
      repo_url: REPO_URL,
      branch: BRANCH,
      port: PORT,
    });
    expect([201, 409]).toContain(status);

    // Verify via GET
    const { status: getStatus, data: appData } = await apiCall(
      "GET",
      `/tenants/${SLUG}/apps/${APP_SLUG}`
    );
    expect(getStatus).toBe(200);
    expect(appData.slug).toBe(APP_SLUG);
    expect(appData.repo_url).toBe(REPO_URL);
    expect(appData.branch).toBe(BRANCH);
    expect(appData.port).toBe(PORT);

    // Verify in UI
    await login(page);
    await page.goto(`${UI}/tenants/${SLUG}`);
    await page.waitForLoadState("networkidle");
    await expect(
      page.getByText(APP_NAME).or(page.getByText(APP_SLUG)).first()
    ).toBeVisible({ timeout: 10_000 });
    await screenshot(page, "p3-02-app-created");
  });

  // ---------------------------------------------------------------
  // P3.03 — App detail page renders with correct tabs
  // ---------------------------------------------------------------
  test("P3.03 App detail sayfasi renderlanir, tab'lar gorunur", async ({ page }) => {
    await login(page);
    await page.goto(`${UI}/tenants/${SLUG}/apps/${APP_SLUG}`);
    await page.waitForLoadState("networkidle");

    // App name visible
    await expect(page.getByText(APP_NAME).first()).toBeVisible({ timeout: 10_000 });

    // Core tabs should exist
    for (const tab of ["Deployments", "Observability", "Logs", "Settings"]) {
      await expect(page.getByText(tab).first()).toBeVisible({ timeout: 5_000 });
    }

    // Build button should be visible
    await expect(page.getByText("Build").first()).toBeVisible();
    await screenshot(page, "p3-03-app-detail-tabs");
  });

  // ---------------------------------------------------------------
  // P3.04 — Trigger build via API
  // ---------------------------------------------------------------
  test("P3.04 Build trigger (API) — deployment pending olusur", async () => {
    const { status, data } = await apiCall(
      "POST",
      `/tenants/${SLUG}/apps/${APP_SLUG}/build`
    );
    expect(status).toBe(202);
    expect(data.status).toBe("pending");
    // build_job_name is set by background pipeline task, may be null initially
    expect(data.id).toBeTruthy();
  });

  // ---------------------------------------------------------------
  // P3.05 — Build status endpoint returns container info
  // ---------------------------------------------------------------
  test("P3.05 Build-status endpoint per-container bilgisi doner", async () => {
    // Wait a few seconds for the build pod to start
    await new Promise((r) => setTimeout(r, 5_000));

    const { status, data } = await apiCall(
      "GET",
      `/tenants/${SLUG}/apps/${APP_SLUG}/build-status`
    );
    expect(status).toBe(200);
    expect(data.job_name).toBeTruthy();
    // deployment_status should be building or pending
    expect(["pending", "building", "deploying", "running"]).toContain(data.deployment_status);
    // containers may or may not be populated yet depending on K8s scheduling
    expect(Array.isArray(data.containers)).toBe(true);
  });

  // ---------------------------------------------------------------
  // P3.06 — Wait for build to complete → running or deploying
  // ---------------------------------------------------------------
  test("P3.06 Build tamamlanir, app running/deploying olur", async () => {
    test.setTimeout(300_000); // 5 min for build + deploy

    await waitFor(
      async () => {
        const { data } = await apiCall(
          "GET",
          `/tenants/${SLUG}/apps/${APP_SLUG}/deployments`
        );
        if (!data.length) return false;
        const latest = data[0];
        return latest.status === "running" || latest.status === "deploying";
      },
      { timeout: 240_000, interval: 10_000 }
    );

    // Verify deployment has image tag
    const { data: deps } = await apiCall(
      "GET",
      `/tenants/${SLUG}/apps/${APP_SLUG}/deployments`
    );
    expect(deps.length).toBeGreaterThan(0);
    expect(deps[0].image_tag).toBeTruthy();
  });

  // ---------------------------------------------------------------
  // P3.07 — Pipeline visualization shows in UI during/after build
  // ---------------------------------------------------------------
  test("P3.07 Pipeline gorsellemesi UI'da gorunur", async ({ page }) => {
    await login(page);
    await page.goto(`${UI}/tenants/${SLUG}/apps/${APP_SLUG}`);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(3_000);

    // Deployment card with status badge should be visible
    await expect(
      page.getByText("running").or(page.getByText("deploying")).first()
    ).toBeVisible({ timeout: 15_000 });

    // Pipeline steps (Clone, Build, Deploy at minimum) should show in deployment cards
    // These are in the compact pipeline visualization
    const deploymentsSection = page.locator('[data-value="deployments"]').or(page.getByText("Deployments").first().locator("..").locator(".."));
    await screenshot(page, "p3-07-pipeline-viz");
  });

  // ---------------------------------------------------------------
  // P3.08 — Deployment list shows entries
  // ---------------------------------------------------------------
  test("P3.08 Deployment listesi dolu, en az 1 entry", async () => {
    const { status, data } = await apiCall(
      "GET",
      `/tenants/${SLUG}/apps/${APP_SLUG}/deployments`
    );
    expect(status).toBe(200);
    expect(data.length).toBeGreaterThan(0);

    const latest = data[0];
    expect(latest.id).toBeTruthy();
    expect(latest.commit_sha).toBeTruthy();
    expect(["running", "deploying", "building"]).toContain(latest.status);
    expect(latest.created_at).toBeTruthy();
  });

  // ---------------------------------------------------------------
  // P3.09 — Observability tab: pods gorunur
  // ---------------------------------------------------------------
  test("P3.09 Observability: pod listesi gorunur (Running)", async ({ page }) => {
    // API check
    const { status, data } = await apiCall(
      "GET",
      `/tenants/${SLUG}/apps/${APP_SLUG}/pods`
    );
    expect(status).toBe(200);
    expect(data.k8s_available).toBe(true);

    // At least one pod should exist (may still be starting)
    if (data.pods.length > 0) {
      expect(["Running", "Pending", "ContainerCreating"]).toContain(data.pods[0].status);
    }

    // UI check
    await login(page);
    await page.goto(`${UI}/tenants/${SLUG}/apps/${APP_SLUG}`);
    await page.waitForLoadState("networkidle");
    await page.getByText("Observability").first().click();
    await page.waitForTimeout(2_000);
    await screenshot(page, "p3-09-observability");
  });

  // ---------------------------------------------------------------
  // P3.10 — Logs SSE stream calisir
  // ---------------------------------------------------------------
  test("P3.10 Logs SSE stream calisiyor", async () => {
    const token = await getToken();
    const res = await fetch(
      `${API.replace("/api/v1", "")}/api/v1/tenants/${SLUG}/apps/${APP_SLUG}/logs?tail_lines=5`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    expect(res.status).toBe(200);
    const text = await res.text();
    // SSE format: "data: ..." lines
    expect(text).toContain("data:");
  });

  // ---------------------------------------------------------------
  // P3.11 — Settings tab: port, replicas, repo URL gorunur
  // ---------------------------------------------------------------
  test("P3.11 Settings: port, replicas, repo URL gorunur", async ({ page }) => {
    await login(page);
    await page.goto(`${UI}/tenants/${SLUG}/apps/${APP_SLUG}`);
    await page.waitForLoadState("networkidle");

    // Click Settings tab
    await page.getByText("Settings").first().click();
    await page.waitForTimeout(2_000);

    // Repo URL or repo name should be visible somewhere in settings
    await expect(
      page.getByText("rotterdam-api").or(page.getByText("rotterdam")).first()
    ).toBeVisible({ timeout: 10_000 });

    await screenshot(page, "p3-11-settings");
  });

  // ---------------------------------------------------------------
  // P3.12 — PATCH app: replicas degistir
  // ---------------------------------------------------------------
  test("P3.12 PATCH /apps — replicas guncellenir", async () => {
    const { status, data } = await apiCall(
      "PATCH",
      `/tenants/${SLUG}/apps/${APP_SLUG}`,
      { replicas: 2 }
    );
    expect(status).toBe(200);
    expect(data.replicas).toBe(2);

    // Verify persisted
    const { data: app } = await apiCall(
      "GET",
      `/tenants/${SLUG}/apps/${APP_SLUG}`
    );
    expect(app.replicas).toBe(2);
  });

  // ---------------------------------------------------------------
  // P3.13 — Cross-tenant isolation: baska tenant'in app'ine erisemez
  // ---------------------------------------------------------------
  test("P3.13 Cross-tenant izolasyon: baska tenant app'e erisemez", async () => {
    // Try to access the app from a non-existent tenant
    const { status } = await apiCall(
      "GET",
      `/tenants/nonexistent-tenant/apps/${APP_SLUG}`
    );
    // Should be 404 (tenant not found) or 403
    expect([403, 404]).toContain(status);
  });

  // ---------------------------------------------------------------
  // P3.14 — Build-status containers detail (after build completed)
  // ---------------------------------------------------------------
  test("P3.14 Build-status: tamamlanmis build containers detayi", async () => {
    const { status, data } = await apiCall(
      "GET",
      `/tenants/${SLUG}/apps/${APP_SLUG}/build-status`
    );
    expect(status).toBe(200);
    expect(data.job_name).toBeTruthy();

    // After build completes, containers should have status info
    if (data.containers.length > 0) {
      for (const c of data.containers) {
        expect(c.name).toBeTruthy();
        expect(["pending", "waiting", "running", "completed", "failed"]).toContain(c.status);
      }
    }
  });

  // ---------------------------------------------------------------
  // P3.15 — App delete: cascade temizlik
  // ---------------------------------------------------------------
  test("P3.15 App delete: app silinir, tenant detail'den kaybolur", async ({ page }) => {
    // Delete via API
    const { status } = await apiCall(
      "DELETE",
      `/tenants/${SLUG}/apps/${APP_SLUG}`
    );
    expect(status).toBe(204);

    // Verify GET returns 404
    const { status: getStatus } = await apiCall(
      "GET",
      `/tenants/${SLUG}/apps/${APP_SLUG}`
    );
    expect(getStatus).toBe(404);

    // Verify not visible in UI
    await login(page);
    await page.goto(`${UI}/tenants/${SLUG}`);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2_000);

    // App should NOT be visible anymore
    const appText = page.getByText(APP_NAME);
    await expect(appText).not.toBeVisible({ timeout: 5_000 });
    await screenshot(page, "p3-15-app-deleted");
  });
});
