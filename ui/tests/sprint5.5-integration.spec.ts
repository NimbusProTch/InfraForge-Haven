/**
 * Sprint 5.5 Playwright E2E — Modals, ConnectedServicesPanel, Wizard Services, Provisioning Banner
 */
import { test, expect } from "@playwright/test";
import {
  mockSession,
  mockGet,
  mockApi,
  TENANT,
  APP,
  DEPLOYMENT,
  PODS,
  EVENTS,
  SERVICE_PG,
  SERVICE_REDIS,
} from "./helpers";

// ── Shared test data ──

const APP_WITH_PENDING = {
  ...APP,
  pending_services: [
    { service_name: "app-pg", service_type: "postgres" },
  ],
};

const APP_NO_PENDING = {
  ...APP,
  pending_services: null,
};

const CONNECTED_SERVICE_PG = {
  service_name: "app-pg",
  service_type: "postgres",
  tier: "dev",
  status: "ready",
  connection_hint: "postgresql://user@host:5432/db",
  database_url_key: "DATABASE_URL",
  connected: true,
  pending: false,
  error_message: null,
};

const CONNECTED_SERVICE_REDIS = {
  service_name: "app-redis",
  service_type: "redis",
  tier: "dev",
  status: "ready",
  connection_hint: "redis://app-redis.tenant-gemeente-test.svc:6379",
  database_url_key: null,
  connected: true,
  pending: false,
  error_message: null,
};

const PENDING_SERVICE = {
  service_name: "app-mongo",
  service_type: "mongodb",
  tier: "dev",
  status: "provisioning",
  connection_hint: null,
  database_url_key: null,
  connected: false,
  pending: true,
  error_message: null,
};

const SYNC_STATUS = { health: "Healthy", sync: "Synced" };

const SYNC_DIFF = [
  {
    kind: "Deployment",
    name: "test-api",
    namespace: "tenant-gemeente-test",
    group: "apps",
    version: "v1",
    sync_status: "OutOfSync",
    health_status: "Healthy",
    health_message: "",
    requires_pruning: false,
  },
];

const DEPLOY_HISTORY = [
  { revision: "abc1234567890", deployedAt: "2026-04-01T12:00:00Z" },
  { revision: "def4567890123", deployedAt: "2026-04-01T10:00:00Z" },
];

const CREDENTIALS_RESPONSE = {
  service_name: "app-pg",
  secret_name: "svc-app-pg",
  connection_hint: "postgresql://user@host:5432/db",
  credentials: {
    POSTGRES_USER: "pguser",
    POSTGRES_PASSWORD: "pgpass123",
    POSTGRES_HOST: "host.svc",
  },
};

const SERVICE_PG_WITH_APPS = {
  ...SERVICE_PG,
  connected_apps: [{ slug: "test-api", name: "Test API" }],
};

const SERVICE_REDIS_WITH_APPS = {
  ...SERVICE_REDIS,
  connected_apps: [],
};

// ── Shared setup for app detail page ──

const appPath = `/tenants/${TENANT.slug}/apps/${APP.slug}`;

async function setupAppDetailPage(
  page: import("@playwright/test").Page,
  appOverride = APP_NO_PENDING,
  services = [CONNECTED_SERVICE_PG, CONNECTED_SERVICE_REDIS]
) {
  await mockSession(page);
  await mockGet(page, `/tenants/${TENANT.slug}`, TENANT);
  await mockGet(page, `/tenants/${TENANT.slug}/apps/${APP.slug}`, appOverride);
  await mockGet(page, `/tenants/${TENANT.slug}/apps/${APP.slug}/deployments`, [DEPLOYMENT]);
  await mockGet(page, `/tenants/${TENANT.slug}/apps/${APP.slug}/pods`, PODS);
  await mockGet(page, `/tenants/${TENANT.slug}/apps/${APP.slug}/events`, EVENTS);
  await mockGet(page, `/tenants/${TENANT.slug}/apps/${APP.slug}/services`, services);
  await mockGet(page, `/tenants/${TENANT.slug}/apps/${APP.slug}/sync-status`, SYNC_STATUS);
  await mockGet(page, `/tenants/${TENANT.slug}/apps/${APP.slug}/sync-diff`, SYNC_DIFF);
  await mockGet(page, `/tenants/${TENANT.slug}/apps/${APP.slug}/deploy-history`, DEPLOY_HISTORY);
  await mockGet(page, `/tenants/${TENANT.slug}/apps/${APP.slug}/build-status`, { status: "idle" });
  await page.route(`**/api/v1/tenants/${TENANT.slug}/apps/${APP.slug}/logs**`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: "data: App started on port 8080\n\ndata: [end]\n\n",
    })
  );
}

/** Navigate to app detail page and wait for content to load */
async function gotoAppDetail(page: import("@playwright/test").Page) {
  await page.goto(appPath);
  // Wait for the app name heading to confirm page loaded
  await expect(page.getByRole("heading", { name: APP.name })).toBeVisible({ timeout: 10_000 });
  // Wait for Scale button to ensure full hydration (buttons are interactive)
  await expect(page.getByRole("button", { name: "Scale" })).toBeVisible({ timeout: 5_000 });
}

// ═══════════════════════════════════════════════════════════════════════════
// 1. ConnectedServicesPanel
// ═══════════════════════════════════════════════════════════════════════════

test.describe("ConnectedServicesPanel", () => {
  test("shows connected services with status badges", async ({ page }) => {
    await setupAppDetailPage(page);
    await gotoAppDetail(page);

    await expect(page.getByText("Connected Services")).toBeVisible();
    await expect(page.getByText("app-pg", { exact: true })).toBeVisible();
    await expect(page.getByText("app-redis", { exact: true })).toBeVisible();
    // Status should be visible
    await expect(page.getByText("ready").first()).toBeVisible();
  });

  test("shows service type and tier info", async ({ page }) => {
    await setupAppDetailPage(page);
    await gotoAppDetail(page);

    await expect(page.getByText("postgres").first()).toBeVisible();
    await expect(page.getByText("redis").first()).toBeVisible();
  });

  test("shows connection hint for connected services", async ({ page }) => {
    await setupAppDetailPage(page);
    await gotoAppDetail(page);

    await expect(page.getByText("postgresql://user@host:5432/db").first()).toBeVisible();
  });

  test("shows pending service with provisioning animation", async ({ page }) => {
    await setupAppDetailPage(page, APP_NO_PENDING, [CONNECTED_SERVICE_PG, PENDING_SERVICE]);
    await gotoAppDetail(page);

    await expect(page.getByText("app-mongo")).toBeVisible();
    await expect(page.getByText("Provisioning...")).toBeVisible();
  });

  test("view credentials button fetches and displays credentials", async ({ page }) => {
    await setupAppDetailPage(page);
    await mockGet(page, `/tenants/${TENANT.slug}/services/app-pg/credentials`, CREDENTIALS_RESPONSE);
    await gotoAppDetail(page);

    // Click the credentials button (Key icon) for app-pg
    const credBtn = page.locator("[title='View credentials']").first();
    await credBtn.click();

    await expect(page.getByText("POSTGRES_USER")).toBeVisible();
    await expect(page.getByText("pguser")).toBeVisible();
    await expect(page.getByText("POSTGRES_PASSWORD")).toBeVisible();
    await expect(page.getByText("pgpass123")).toBeVisible();
  });

  test("disconnect button calls API and refreshes", async ({ page }) => {
    let disconnectCalled = false;
    await setupAppDetailPage(page);
    await mockApi(
      page,
      `/tenants/${TENANT.slug}/apps/${APP.slug}/connect-service/app-pg`,
      (route) => {
        if (route.request().method() === "DELETE") {
          disconnectCalled = true;
          route.fulfill({ status: 204 });
        } else {
          route.fallback();
        }
      }
    );
    await gotoAppDetail(page);

    const disconnectBtn = page.locator("[title='Disconnect service']").first();
    await disconnectBtn.click();

    await page.waitForTimeout(500);
    expect(disconnectCalled).toBe(true);
  });

  test("panel hidden when no services", async ({ page }) => {
    await setupAppDetailPage(page, APP_NO_PENDING, []);
    await gotoAppDetail(page);

    await expect(page.getByText("Connected Services")).not.toBeVisible();
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// 2. Provisioning Banner
// ═══════════════════════════════════════════════════════════════════════════

test.describe("Provisioning Banner", () => {
  test("shows banner when app has pending services", async ({ page }) => {
    await setupAppDetailPage(page, APP_WITH_PENDING);
    await gotoAppDetail(page);

    await expect(page.getByText("Services provisioning:")).toBeVisible();
    await expect(page.getByText("app-pg (postgres)")).toBeVisible();
    await expect(page.getByText("Build is available but deploy may fail")).toBeVisible();
  });

  test("no banner when no pending services", async ({ page }) => {
    await setupAppDetailPage(page, APP_NO_PENDING);
    await gotoAppDetail(page);

    await expect(page.getByText("Services provisioning:")).not.toBeVisible();
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// 3. ScaleModal
// ═══════════════════════════════════════════════════════════════════════════

test.describe("ScaleModal", () => {
  test("opens on Scale button click and shows replica presets", async ({ page }) => {
    await setupAppDetailPage(page);
    await gotoAppDetail(page);

    await page.getByRole("button", { name: "Scale" }).click();

    // Modal title
    await expect(page.getByText(`Scale: ${APP.slug}`)).toBeVisible();
    // Replica presets (1, 2, 3, 5)
    await expect(page.getByRole("button", { name: "1", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "2", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "3", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "5", exact: true })).toBeVisible();
  });

  test("shows resource tiers (Starter, Standard, Performance)", async ({ page }) => {
    await setupAppDetailPage(page);
    await gotoAppDetail(page);

    await page.getByRole("button", { name: "Scale" }).click();

    await expect(page.getByText("Starter")).toBeVisible();
    await expect(page.getByText("Standard")).toBeVisible();
    await expect(page.getByText("Performance")).toBeVisible();
  });

  test("shows impact preview", async ({ page }) => {
    await setupAppDetailPage(page);
    await gotoAppDetail(page);

    await page.getByRole("button", { name: "Scale" }).click();

    await expect(page.getByText("Impact Preview")).toBeVisible();
    await expect(page.getByText("Pods:")).toBeVisible();
  });

  test("HPA toggle shows min/max/target inputs", async ({ page }) => {
    await setupAppDetailPage(page);
    await gotoAppDetail(page);

    await page.getByRole("button", { name: "Scale" }).click();

    await expect(page.getByText("Auto-scaling (HPA)")).toBeVisible();
    // Since min != max in APP (1 != 5), HPA is enabled by default
    await expect(page.getByText("Min")).toBeVisible();
    await expect(page.getByText("Max")).toBeVisible();
    await expect(page.getByText("CPU Target")).toBeVisible();
  });

  test("Apply Changes button calls PATCH API", async ({ page }) => {
    let patchCalled = false;
    await setupAppDetailPage(page);
    // Use mockApi to handle PATCH on the app endpoint
    await mockApi(page, `/tenants/${TENANT.slug}/apps/${APP.slug}`, (route) => {
      if (route.request().method() === "PATCH") {
        patchCalled = true;
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ ...APP, replicas: 3 }),
        });
      } else if (route.request().method() === "GET") {
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(APP_NO_PENDING),
        });
      } else {
        route.fallback();
      }
    });
    await gotoAppDetail(page);

    await page.getByRole("button", { name: "Scale" }).click();
    await page.getByRole("button", { name: "3", exact: true }).click();
    await page.getByRole("button", { name: "Apply Changes" }).click();

    await page.waitForTimeout(500);
    expect(patchCalled).toBe(true);
  });

  test("Cancel closes modal", async ({ page }) => {
    await setupAppDetailPage(page);
    await gotoAppDetail(page);

    await page.getByRole("button", { name: "Scale" }).click();
    await expect(page.getByText(`Scale: ${APP.slug}`)).toBeVisible();

    await page.getByRole("button", { name: "Cancel" }).first().click();
    await expect(page.getByText(`Scale: ${APP.slug}`)).not.toBeVisible();
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// 4. SyncModal — REMOVED (P2.3 / H3c)
// ═══════════════════════════════════════════════════════════════════════════
//
// The SyncModal component (ui/components/SyncModal.tsx) was deleted in
// Sprint H3 (P2.3) — it had zero imports across the UI codebase, so its
// 7 Playwright tests were testing a hypothetical UI that did not exist.
// Removing the test block here, the dead component file, and the
// `api.sync*` API client methods all together.

// ═══════════════════════════════════════════════════════════════════════════
// 5. RestartModal
// ═══════════════════════════════════════════════════════════════════════════

test.describe("RestartModal", () => {
  test("opens on Restart button and shows pod count", async ({ page }) => {
    await setupAppDetailPage(page);
    await gotoAppDetail(page);

    await page.getByRole("button", { name: "Restart" }).click();

    await expect(page.getByText(`Restart: ${APP.slug}`)).toBeVisible();
    await expect(page.getByText(`${APP.replicas} pods running`)).toBeVisible();
  });

  test("shows namespace info", async ({ page }) => {
    await setupAppDetailPage(page);
    await gotoAppDetail(page);

    await page.getByRole("button", { name: "Restart" }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText(TENANT.namespace)).toBeVisible();
  });

  test("shows rolling restart warning", async ({ page }) => {
    await setupAppDetailPage(page);
    await gotoAppDetail(page);

    await page.getByRole("button", { name: "Restart" }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText("Rolling restart", { exact: true })).toBeVisible();
    await expect(dialog.getByText("zero downtime")).toBeVisible();
  });

  test("single replica warns about brief downtime", async ({ page }) => {
    await setupAppDetailPage(page, { ...APP_NO_PENDING, replicas: 1 });
    await gotoAppDetail(page);

    await page.getByRole("button", { name: "Restart" }).click();

    await expect(page.getByText("brief downtime")).toBeVisible();
  });

  test("Restart Pods button calls API", async ({ page }) => {
    let restartCalled = false;
    await setupAppDetailPage(page);
    await mockApi(page, `/tenants/${TENANT.slug}/apps/${APP.slug}/restart`, (route) => {
      if (route.request().method() === "POST") {
        restartCalled = true;
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ status: "restarting", app_slug: APP.slug }),
        });
      } else {
        route.fallback();
      }
    });
    await gotoAppDetail(page);

    await page.getByRole("button", { name: "Restart" }).click();
    await page.getByRole("button", { name: "Restart Pods" }).click();

    await page.waitForTimeout(500);
    expect(restartCalled).toBe(true);
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// 6. Wizard Step 5 — Services
// ═══════════════════════════════════════════════════════════════════════════

test.describe("Wizard Step 5 - Services", () => {
  const newAppPath = `/tenants/${TENANT.slug}/apps/new`;

  async function setupWizard(page: import("@playwright/test").Page) {
    await mockSession(page);
    await mockGet(page, `/tenants/${TENANT.slug}`, TENANT);
    await mockGet(page, `/tenants/${TENANT.slug}/apps`, []);
    await mockGet(page, `/tenants/${TENANT.slug}/services`, []);
    // Mock GitHub repos and branches
    await page.route(`**/api/v1/tenants/${TENANT.slug}/github/repos**`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      })
    );
  }

  async function navigateToStep5(page: import("@playwright/test").Page) {
    await page.goto(newAppPath);
    await expect(page.getByRole("heading", { name: "New Application" })).toBeVisible({ timeout: 10_000 });

    // Step 1: Identity — fill Application Name (auto-generates slug)
    await page.locator("input[placeholder='My Application']").fill("my-test-app");

    // Click Next → Step 2 (Source Code)
    await page.getByRole("button", { name: "Next" }).click();

    // Step 2: Switch to manual mode and fill repo URL
    await page.getByText("Enter manually").click();
    await page.locator("input[placeholder='https://github.com/owner/repo']").fill(
      "https://github.com/test/repo"
    );

    // Click Next → Step 3 (Build)
    await page.getByRole("button", { name: "Next" }).click();

    // Step 3: Build — port defaults to 8000, just click Next
    await page.getByRole("button", { name: "Next" }).click();

    // Step 4: Runtime — click Next
    await page.getByRole("button", { name: "Next" }).click();

    // Now on Step 5: Services
    await expect(page.getByText("Services").first()).toBeVisible();
  }

  test("services step shows all 5 service types", async ({ page }) => {
    await setupWizard(page);
    await navigateToStep5(page);

    await expect(page.getByText("PostgreSQL")).toBeVisible();
    await expect(page.getByText("MySQL")).toBeVisible();
    await expect(page.getByText("MongoDB")).toBeVisible();
    await expect(page.getByText("Redis")).toBeVisible();
    await expect(page.getByText("RabbitMQ")).toBeVisible();
  });

  test("selecting a service shows it in selected list", async ({ page }) => {
    await setupWizard(page);
    await navigateToStep5(page);

    // Click PostgreSQL card
    await page.getByText("PostgreSQL").click();

    // Should show selected services section
    await expect(page.getByText("Selected Services (1)")).toBeVisible();
  });

  test("selected services appear in review step", async ({ page }) => {
    await setupWizard(page);
    await navigateToStep5(page);

    // Select PostgreSQL
    await page.getByText("PostgreSQL").click();
    // Select Redis
    await page.getByText("Redis").click();

    // Go to Review
    await page.getByRole("button", { name: "Review" }).click();

    // Review should show Services section with icons
    await expect(page.getByText("Services").last()).toBeVisible();
  });

  test("deselecting a service removes it", async ({ page }) => {
    await setupWizard(page);
    await navigateToStep5(page);

    // Select PostgreSQL
    await page.getByText("PostgreSQL").click();
    await expect(page.getByText("Selected Services (1)")).toBeVisible();

    // Click again to deselect
    await page.getByText("PostgreSQL").click();
    await expect(page.getByText("Selected Services")).not.toBeVisible();
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// 7. Tenant Services — connected_apps
// ═══════════════════════════════════════════════════════════════════════════

test.describe("Tenant Services - connected_apps", () => {
  test.beforeEach(async ({ page }) => {
    await mockSession(page);
    await mockGet(page, `/tenants/${TENANT.slug}`, TENANT);
    await mockGet(page, `/tenants/${TENANT.slug}/apps`, [APP]);
    await mockGet(page, `/tenants/${TENANT.slug}/services`, [
      SERVICE_PG_WITH_APPS,
      SERVICE_REDIS_WITH_APPS,
    ]);
  });

  test("shows connected apps for a service", async ({ page }) => {
    await page.goto(`/tenants/${TENANT.slug}`);
    await page.getByText("Services").first().click();

    await expect(page.getByText("Connected to:")).toBeVisible();
    await expect(page.getByText("Test API").first()).toBeVisible();
  });

  test("service without connected apps does not show badge", async ({ page }) => {
    await mockGet(page, `/tenants/${TENANT.slug}/services`, [SERVICE_REDIS_WITH_APPS]);
    await page.goto(`/tenants/${TENANT.slug}`);
    await page.getByText("Services").first().click();

    await expect(page.getByText("Connected to:")).not.toBeVisible();
  });
});
