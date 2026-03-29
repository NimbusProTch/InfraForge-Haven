import { test, expect } from "@playwright/test";
import { getApiToken, apiCall, cleanupTenant } from "../helpers/api";

const TENANT_SLUG = "pw-api-test";

test.describe("Backend API CRUD Tests", () => {
  let token: string;

  test.beforeAll(async ({ request }) => {
    token = await getApiToken(request);
    await cleanupTenant(request, token, TENANT_SLUG);
  });

  test.afterAll(async ({ request }) => {
    token = await getApiToken(request);
    await cleanupTenant(request, token, TENANT_SLUG);
  });

  test("create tenant", async ({ request }) => {
    const resp = await apiCall(request, "POST", "/tenants", token, {
      name: "PW API Test",
      slug: TENANT_SLUG,
    });
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data.slug).toBe(TENANT_SLUG);
    expect(data.namespace).toBe(`tenant-${TENANT_SLUG}`);
  });

  test("get tenant", async ({ request }) => {
    const resp = await apiCall(request, "GET", `/tenants/${TENANT_SLUG}`, token);
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data.name).toBe("PW API Test");
  });

  test("list tenants includes new one", async ({ request }) => {
    const resp = await apiCall(request, "GET", "/tenants", token);
    const data = await resp.json();
    const slugs = data.map((t: { slug: string }) => t.slug);
    expect(slugs).toContain(TENANT_SLUG);
  });

  test("create app", async ({ request }) => {
    const resp = await apiCall(request, "POST", `/tenants/${TENANT_SLUG}/apps`, token, {
      name: "Test App",
      slug: "test-app",
      repo_url: "https://github.com/test/repo",
      branch: "main",
      port: 3000,
    });
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data.slug).toBe("test-app");
    expect(data.port).toBe(3000);
    expect(data.webhook_token).toBeTruthy();
  });

  test("update app", async ({ request }) => {
    const resp = await apiCall(request, "PATCH", `/tenants/${TENANT_SLUG}/apps/test-app`, token, {
      replicas: 3,
      env_vars: { NODE_ENV: "production", PORT: "3000" },
    });
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data.replicas).toBe(3);
    expect(data.env_vars.NODE_ENV).toBe("production");
  });

  test("add member", async ({ request }) => {
    const resp = await apiCall(request, "POST", `/tenants/${TENANT_SLUG}/members`, token, {
      email: "jan@test.nl",
      role: "member",
      user_id: "pw-user-1",
      display_name: "Jan",
    });
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data.email).toBe("jan@test.nl");
    expect(data.role).toBe("member");
  });

  test("list members", async ({ request }) => {
    const resp = await apiCall(request, "GET", `/tenants/${TENANT_SLUG}/members`, token);
    const data = await resp.json();
    expect(data.length).toBeGreaterThanOrEqual(1);
  });

  test("create environment", async ({ request }) => {
    const resp = await apiCall(request, "POST", `/tenants/${TENANT_SLUG}/apps/test-app/environments`, token, {
      name: "staging",
      env_type: "staging",
      branch: "develop",
    });
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data.name).toBe("staging");
    expect(data.env_type).toBe("staging");
    expect(data.domain).toContain("staging");
  });

  test("add custom domain", async ({ request }) => {
    const resp = await apiCall(request, "POST", `/tenants/${TENANT_SLUG}/apps/test-app/domains`, token, {
      domain: "test.example.nl",
    });
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data.domain).toBe("test.example.nl");
    expect(data.verification_token).toBeTruthy();
  });

  test("list domains", async ({ request }) => {
    const resp = await apiCall(request, "GET", `/tenants/${TENANT_SLUG}/apps/test-app/domains`, token);
    const data = await resp.json();
    expect(data.length).toBe(1);
    expect(data[0].domain).toBe("test.example.nl");
  });

  test("delete app", async ({ request }) => {
    const resp = await apiCall(request, "DELETE", `/tenants/${TENANT_SLUG}/apps/test-app`, token);
    expect(resp.status()).toBe(204);
  });

  test("delete tenant", async ({ request }) => {
    const resp = await apiCall(request, "DELETE", `/tenants/${TENANT_SLUG}`, token);
    expect(resp.status()).toBe(204);
  });

  test("verify tenant gone", async ({ request }) => {
    const resp = await apiCall(request, "GET", `/tenants/${TENANT_SLUG}`, token);
    expect(resp.status()).toBe(404);
  });
});
