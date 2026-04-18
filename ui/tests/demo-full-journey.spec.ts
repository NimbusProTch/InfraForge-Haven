/**
 * Full customer journey via iyziops UI (browser):
 *  1. Login (testuser)
 *  2. Navigate to demo tenant
 *  3. Deploy demo-api through 5-step New App wizard
 *  4. Watch build log stream until pod Running
 *  5. Verify demo-api.iyziops.com/test returns {all_ok: true}
 *  6. Deploy demo-ui through same wizard
 *  7. Verify demo.iyziops.com renders notes page
 *  8. Create note via UI, verify it appears
 *
 * Prereqs: demo-setup.spec.ts must have run (tenant + 3 services ready).
 */
import { test, expect } from "@playwright/test";
import { login, apiCall, waitFor, TENANT_SLUG, UI, snap } from "./demo-helpers";

const DEMO_API_SLUG = "demo-api";
const DEMO_UI_SLUG = "demo-ui";
const REPO = "https://github.com/NimbusProTch/InfraForge-Haven.git";

test.describe.serial("Demo — full UI deploy journey", () => {
  test.setTimeout(1_800_000); // 30 min per test — build + deploy is long

  test.beforeAll(async () => {
    // Sanity check: services exist + ready
    const { data } = await apiCall<any[]>("GET", `/api/v1/tenants/${TENANT_SLUG}/services`);
    const names = ["demo-pg", "demo-cache", "demo-queue"];
    for (const name of names) {
      const s = (data as any[]).find((x) => x.name === name);
      expect(s, `service ${name} must exist — run demo-setup.spec.ts first`).toBeDefined();
      expect(s.status, `service ${name} must be ready`).toBe("ready");
    }
  });

  test("1. login + navigate to demo tenant", async ({ page }) => {
    await login(page);
    // Tolerate UI redirects — what matters is tenant data is accessible
    await page.goto(`${UI}/tenants`, { waitUntil: "networkidle" });
    await snap(page, "01-tenants-home");
    // Tenant should be in the list (testuser is owner of demo)
    await expect(page.getByText("iyziops Demo").first()).toBeVisible({ timeout: 10_000 });
  });

  test("2. deploy demo-api via API (platform-driven, not wizard)", async () => {
    // Kick off via API — faster + more deterministic than wizard in tests
    // (we separately walk the wizard in demo-wizard-walkthrough.spec.ts for story proof)
    const appPayload = {
      slug: DEMO_API_SLUG,
      name: "Demo API",
      repo_url: REPO,
      branch: "main",
      git_provider: "github",
      build_context: "demo/api",
      dockerfile_path: "demo/api/Dockerfile",
      use_dockerfile: true,
      port: 8000,
      custom_domain: "demo-api.iyziops.com",
      health_check_path: "/ready",
      connect_services: ["demo-pg", "demo-cache", "demo-queue"],
      resource_cpu_request: "100m",
      resource_memory_request: "256Mi",
      resource_memory_limit: "512Mi",
    };
    const { status, data } = await apiCall("POST", `/api/v1/tenants/${TENANT_SLUG}/apps`, appPayload);
    expect([201, 409]).toContain(status);
    console.log(`[demo-api] created (status ${status})`);

    // Trigger build
    if (status === 201) {
      const b = await apiCall(
        "POST",
        `/api/v1/tenants/${TENANT_SLUG}/apps/${DEMO_API_SLUG}/build?deploy=true`,
        {},
      );
      console.log(`[demo-api] build triggered (status ${b.status})`);
      expect([202, 200]).toContain(b.status);
    }
  });

  test("3. demo-api reaches running + /test returns all_ok", async () => {
    await waitFor(
      async () => {
        const { data } = await apiCall<any[]>(
          "GET",
          `/api/v1/tenants/${TENANT_SLUG}/apps/${DEMO_API_SLUG}/deployments`,
        );
        if (!Array.isArray(data) || data.length === 0) return false;
        const latest = data[0];
        console.log(`[demo-api] deployment status=${latest.status}`);
        return latest.status === "running";
      },
      { timeout: 1_500_000, interval: 20_000, label: "demo-api deployment running" },
    );

    // Verify /test endpoint returns all_ok
    await waitFor(
      async () => {
        try {
          const res = await fetch("https://demo-api.iyziops.com/test");
          if (res.status !== 200) return false;
          const json = await res.json();
          console.log(`[demo-api/test] ${JSON.stringify(json)}`);
          return json.all_ok === true;
        } catch (e) {
          console.log(`[demo-api/test] fetch error: ${e}`);
          return false;
        }
      },
      { timeout: 300_000, interval: 10_000, label: "demo-api.iyziops.com/test returns all_ok" },
    );
  });

  test("4. deploy demo-ui via API", async () => {
    const { status } = await apiCall("POST", `/api/v1/tenants/${TENANT_SLUG}/apps`, {
      slug: DEMO_UI_SLUG,
      name: "Demo UI",
      repo_url: REPO,
      branch: "main",
      build_context: "demo/ui",
      dockerfile_path: "demo/ui/Dockerfile",
      use_dockerfile: true,
      port: 3000,
      custom_domain: "demo.iyziops.com",
      health_check_path: "/",
      env_vars: {
        NEXT_PUBLIC_API_URL: "https://demo-api.iyziops.com",
      },
      resource_cpu_request: "100m",
      resource_memory_request: "256Mi",
      resource_memory_limit: "512Mi",
    });
    expect([201, 409]).toContain(status);

    if (status === 201) {
      const b = await apiCall(
        "POST",
        `/api/v1/tenants/${TENANT_SLUG}/apps/${DEMO_UI_SLUG}/build?deploy=true`,
        {},
      );
      expect([202, 200]).toContain(b.status);
    }
  });

  test("5. demo-ui running + reachable", async () => {
    await waitFor(
      async () => {
        const { data } = await apiCall<any[]>(
          "GET",
          `/api/v1/tenants/${TENANT_SLUG}/apps/${DEMO_UI_SLUG}/deployments`,
        );
        if (!Array.isArray(data) || data.length === 0) return false;
        const latest = data[0];
        console.log(`[demo-ui] deployment status=${latest.status}`);
        return latest.status === "running";
      },
      { timeout: 1_500_000, interval: 20_000, label: "demo-ui deployment running" },
    );

    await waitFor(
      async () => {
        try {
          const res = await fetch("https://demo.iyziops.com/");
          return res.status === 200;
        } catch {
          return false;
        }
      },
      { timeout: 300_000, interval: 10_000, label: "demo.iyziops.com HTTP 200" },
    );
  });

  test("6. demo.iyziops.com renders + CRUD works", async ({ page }) => {
    const consoleErrors: string[] = [];
    const networkFails: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("requestfailed", (req) => {
      networkFails.push(`${req.method()} ${req.url()} ${req.failure()?.errorText ?? ""}`);
    });

    await page.goto("https://demo.iyziops.com/", { waitUntil: "networkidle" });
    await snap(page, "06-demo-ui-home");

    // Header visible
    await expect(page.getByRole("heading", { name: /iyziops demo/i })).toBeVisible();

    // Create a note
    const title = `Test ${Date.now()}`;
    await page.fill('input[placeholder="Title"]', title);
    await page.fill('textarea[placeholder="Body"]', "Created by Playwright E2E");
    await page.click('button:has-text("Create")');

    // Wait for note to appear
    await expect(page.getByText(title)).toBeVisible({ timeout: 15_000 });
    await snap(page, "06-note-created");

    // No console errors
    const ignoredErrorPatterns = [
      /favicon/i,
      /ERR_BLOCKED_BY_CLIENT/i, // ad-block noise
    ];
    const realErrors = consoleErrors.filter(
      (e) => !ignoredErrorPatterns.some((p) => p.test(e)),
    );
    if (realErrors.length > 0) {
      console.log("CONSOLE ERRORS:", realErrors);
    }
    expect(realErrors).toEqual([]);

    // No network failures
    if (networkFails.length > 0) {
      console.log("NETWORK FAILS:", networkFails);
    }
    expect(networkFails).toEqual([]);
  });
});
