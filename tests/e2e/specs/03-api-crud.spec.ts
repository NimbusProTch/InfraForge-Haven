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

// ---------------------------------------------------------------------------
// PostgreSQL Managed Service — Full Lifecycle (Sprint B)
// Uses existing tenant + app that are already provisioned on the cluster.
// ---------------------------------------------------------------------------
const PG_TENANT = "testing";
const PG_SERVICE = "e2e-pg";
const PG_APP = "test";

test.describe("PostgreSQL Service Lifecycle", () => {
  let token: string;

  test.beforeAll(async ({ request }) => {
    token = await getApiToken(request);
    // Cleanup from previous runs (delete service if it exists)
    await apiCall(request, "DELETE", `/tenants/${PG_TENANT}/services/${PG_SERVICE}`, token);
  });

  test.afterAll(async ({ request }) => {
    token = await getApiToken(request);
    // Cleanup: delete service and disconnect from app
    await apiCall(request, "DELETE", `/tenants/${PG_TENANT}/apps/${PG_APP}/connect-service/${PG_SERVICE}`, token);
    await apiCall(request, "DELETE", `/tenants/${PG_TENANT}/services/${PG_SERVICE}`, token);
  });

  test("create PostgreSQL service returns 201 with provisioning status", async ({ request }) => {
    const resp = await apiCall(request, "POST", `/tenants/${PG_TENANT}/services`, token, {
      name: PG_SERVICE,
      service_type: "postgres",
      tier: "dev",
    });
    expect(resp.ok()).toBeTruthy();
    expect(resp.status()).toBe(201);
    const data = await resp.json();
    expect(data.name).toBe(PG_SERVICE);
    expect(data.service_type).toBe("postgres");
    expect(data.status).toBe("provisioning");
    expect(data.connection_hint).toBeTruthy();
    expect(data.connection_hint).toContain("postgresql://");
    expect(data.secret_name).toBeTruthy();
  });

  test("poll until PostgreSQL is ready", async ({ request }) => {
    // Poll every 5s for up to 120s
    const maxWait = 120_000;
    const interval = 5_000;
    const start = Date.now();
    let status = "provisioning";

    while (Date.now() - start < maxWait) {
      const resp = await apiCall(request, "GET", `/tenants/${PG_TENANT}/services/${PG_SERVICE}`, token);
      expect(resp.ok()).toBeTruthy();
      const data = await resp.json();
      status = data.status;
      if (status === "ready") break;
      if (status === "failed") throw new Error(`Service failed: ${data.error_message}`);
      await new Promise((r) => setTimeout(r, interval));
    }

    expect(status).toBe("ready");
  });

  test("get service detail includes runtime info", async ({ request }) => {
    const resp = await apiCall(request, "GET", `/tenants/${PG_TENANT}/services/${PG_SERVICE}`, token);
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data.status).toBe("ready");
    expect(data.connection_hint).toContain("postgresql://");
    // Runtime details should be populated for Everest-managed PG
    if (data.runtime) {
      expect(data.runtime.engine_version).toBeTruthy();
      expect(data.runtime.hostname).toBeTruthy();
      expect(data.runtime.port).toBeTruthy();
    }
  });

  test("get credentials returns decoded secrets", async ({ request }) => {
    const resp = await apiCall(request, "GET", `/tenants/${PG_TENANT}/services/${PG_SERVICE}/credentials`, token);
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data.service_name).toBe(PG_SERVICE);
    expect(data.secret_name).toBeTruthy();
    expect(data.credentials).toBeTruthy();
    // Everest PG secrets should have these keys
    const keys = Object.keys(data.credentials);
    expect(keys.length).toBeGreaterThan(0);
    // At minimum: username/password or similar credential keys
    const hasAuth = keys.some((k) => ["username", "password", "user", "pgbouncer-host", "host"].includes(k));
    expect(hasAuth).toBeTruthy();
  });

  test("connect service to app injects DATABASE_URL", async ({ request }) => {
    const resp = await apiCall(
      request,
      "POST",
      `/tenants/${PG_TENANT}/apps/${PG_APP}/connect-service`,
      token,
      { service_name: PG_SERVICE }
    );
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    // env_from_secrets should have the connection entry
    expect(data.env_from_secrets).toBeTruthy();
    expect(data.env_from_secrets.length).toBe(1);
    expect(data.env_from_secrets[0].service_name).toBe(PG_SERVICE);
    // DATABASE_URL must be injected into env_vars
    expect(data.env_vars).toBeTruthy();
    expect(data.env_vars.DATABASE_URL).toBeTruthy();
    expect(data.env_vars.DATABASE_URL).toContain("postgresql://");
  });

  test("disconnect service removes DATABASE_URL", async ({ request }) => {
    const resp = await apiCall(
      request,
      "DELETE",
      `/tenants/${PG_TENANT}/apps/${PG_APP}/connect-service/${PG_SERVICE}`,
      token
    );
    expect(resp.status()).toBe(204);

    // Verify DATABASE_URL is gone from app
    const appResp = await apiCall(request, "GET", `/tenants/${PG_TENANT}/apps/${PG_APP}`, token);
    expect(appResp.ok()).toBeTruthy();
    const appData = await appResp.json();
    const envVars = appData.env_vars || {};
    expect(envVars.DATABASE_URL).toBeUndefined();
    // env_from_secrets should be empty
    expect(appData.env_from_secrets || []).toHaveLength(0);
  });

  test("delete PostgreSQL service", async ({ request }) => {
    const resp = await apiCall(request, "DELETE", `/tenants/${PG_TENANT}/services/${PG_SERVICE}`, token);
    expect(resp.status()).toBe(204);
  });

  test("verify service gone after delete", async ({ request }) => {
    const resp = await apiCall(request, "GET", `/tenants/${PG_TENANT}/services/${PG_SERVICE}`, token);
    expect(resp.status()).toBe(404);
  });
});

// ---------------------------------------------------------------------------
// MySQL Managed Service — Full Lifecycle (Sprint B3)
// ---------------------------------------------------------------------------
const MYSQL_TENANT = "testing";
const MYSQL_SERVICE = "e2e-mysql";
const MYSQL_APP = "test";

test.describe("MySQL Service Lifecycle", () => {
  let token: string;

  test.beforeAll(async ({ request }) => {
    token = await getApiToken(request);
    await apiCall(request, "DELETE", `/tenants/${MYSQL_TENANT}/services/${MYSQL_SERVICE}`, token);
  });

  test.afterAll(async ({ request }) => {
    token = await getApiToken(request);
    await apiCall(request, "DELETE", `/tenants/${MYSQL_TENANT}/apps/${MYSQL_APP}/connect-service/${MYSQL_SERVICE}`, token);
    await apiCall(request, "DELETE", `/tenants/${MYSQL_TENANT}/services/${MYSQL_SERVICE}`, token);
  });

  test("create MySQL service returns 201", async ({ request }) => {
    const resp = await apiCall(request, "POST", `/tenants/${MYSQL_TENANT}/services`, token, {
      name: MYSQL_SERVICE,
      service_type: "mysql",
      tier: "dev",
    });
    expect(resp.ok()).toBeTruthy();
    expect(resp.status()).toBe(201);
    const data = await resp.json();
    expect(data.name).toBe(MYSQL_SERVICE);
    expect(data.service_type).toBe("mysql");
    expect(data.status).toBe("provisioning");
    expect(data.connection_hint).toContain("mysql://");
    expect(data.secret_name).toContain("testing-e2e-mysql");
  });

  test("poll until MySQL is ready", async ({ request }) => {
    // MySQL XtraDB + Galera takes ~3-4 minutes to initialize
    const maxWait = 360_000;
    const interval = 10_000;
    const start = Date.now();
    let status = "provisioning";

    while (Date.now() - start < maxWait) {
      const resp = await apiCall(request, "GET", `/tenants/${MYSQL_TENANT}/services/${MYSQL_SERVICE}`, token);
      expect(resp.ok()).toBeTruthy();
      const data = await resp.json();
      status = data.status;
      if (status === "ready") break;
      if (status === "failed") throw new Error(`MySQL failed: ${data.error_message}`);
      await new Promise((r) => setTimeout(r, interval));
    }
    expect(status).toBe("ready");
  });

  test("get MySQL credentials", async ({ request }) => {
    const resp = await apiCall(request, "GET", `/tenants/${MYSQL_TENANT}/services/${MYSQL_SERVICE}/credentials`, token);
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data.service_name).toBe(MYSQL_SERVICE);
    expect(Object.keys(data.credentials).length).toBeGreaterThan(0);
  });

  test("connect MySQL to app injects MYSQL_URL and DATABASE_URL", async ({ request }) => {
    const resp = await apiCall(request, "POST", `/tenants/${MYSQL_TENANT}/apps/${MYSQL_APP}/connect-service`, token, {
      service_name: MYSQL_SERVICE,
    });
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data.env_vars.MYSQL_URL).toBeTruthy();
    expect(data.env_vars.MYSQL_URL).toContain("mysql://");
    expect(data.env_vars.DATABASE_URL).toBeTruthy();
    expect(data.env_vars.DATABASE_URL).toContain("mysql://");
  });

  test("disconnect MySQL removes MYSQL_URL and DATABASE_URL", async ({ request }) => {
    await apiCall(request, "DELETE", `/tenants/${MYSQL_TENANT}/apps/${MYSQL_APP}/connect-service/${MYSQL_SERVICE}`, token);
    const appResp = await apiCall(request, "GET", `/tenants/${MYSQL_TENANT}/apps/${MYSQL_APP}`, token);
    const env = (await appResp.json()).env_vars || {};
    expect(env.MYSQL_URL).toBeUndefined();
    expect(env.DATABASE_URL).toBeUndefined();
  });

  test("delete MySQL service", async ({ request }) => {
    const resp = await apiCall(request, "DELETE", `/tenants/${MYSQL_TENANT}/services/${MYSQL_SERVICE}`, token);
    expect(resp.status()).toBe(204);
  });

  test("verify MySQL gone", async ({ request }) => {
    const resp = await apiCall(request, "GET", `/tenants/${MYSQL_TENANT}/services/${MYSQL_SERVICE}`, token);
    expect(resp.status()).toBe(404);
  });
});

// ---------------------------------------------------------------------------
// MongoDB Managed Service — Full Lifecycle (Sprint B3)
// ---------------------------------------------------------------------------
const MONGO_TENANT = "testing";
const MONGO_SERVICE = "e2e-mongo";
const MONGO_APP = "test";

test.describe("MongoDB Service Lifecycle", () => {
  let token: string;

  test.beforeAll(async ({ request }) => {
    token = await getApiToken(request);
    await apiCall(request, "DELETE", `/tenants/${MONGO_TENANT}/services/${MONGO_SERVICE}`, token);
  });

  test.afterAll(async ({ request }) => {
    token = await getApiToken(request);
    await apiCall(request, "DELETE", `/tenants/${MONGO_TENANT}/apps/${MONGO_APP}/connect-service/${MONGO_SERVICE}`, token);
    await apiCall(request, "DELETE", `/tenants/${MONGO_TENANT}/services/${MONGO_SERVICE}`, token);
  });

  test("create MongoDB service returns 201", async ({ request }) => {
    const resp = await apiCall(request, "POST", `/tenants/${MONGO_TENANT}/services`, token, {
      name: MONGO_SERVICE,
      service_type: "mongodb",
      tier: "dev",
    });
    expect(resp.ok()).toBeTruthy();
    expect(resp.status()).toBe(201);
    const data = await resp.json();
    expect(data.name).toBe(MONGO_SERVICE);
    expect(data.service_type).toBe("mongodb");
    expect(data.status).toBe("provisioning");
    expect(data.connection_hint).toContain("mongodb://");
    expect(data.secret_name).toContain("testing-e2e-mongo");
  });

  test("poll until MongoDB is ready", async ({ request }) => {
    const maxWait = 180_000;
    const interval = 5_000;
    const start = Date.now();
    let status = "provisioning";

    while (Date.now() - start < maxWait) {
      const resp = await apiCall(request, "GET", `/tenants/${MONGO_TENANT}/services/${MONGO_SERVICE}`, token);
      expect(resp.ok()).toBeTruthy();
      const data = await resp.json();
      status = data.status;
      if (status === "ready") break;
      if (status === "failed") throw new Error(`MongoDB failed: ${data.error_message}`);
      await new Promise((r) => setTimeout(r, interval));
    }
    expect(status).toBe("ready");
  });

  test("get MongoDB credentials", async ({ request }) => {
    const resp = await apiCall(request, "GET", `/tenants/${MONGO_TENANT}/services/${MONGO_SERVICE}/credentials`, token);
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data.service_name).toBe(MONGO_SERVICE);
    expect(Object.keys(data.credentials).length).toBeGreaterThan(0);
  });

  test("connect MongoDB to app injects MONGODB_URL and DATABASE_URL", async ({ request }) => {
    const resp = await apiCall(request, "POST", `/tenants/${MONGO_TENANT}/apps/${MONGO_APP}/connect-service`, token, {
      service_name: MONGO_SERVICE,
    });
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data.env_vars.MONGODB_URL).toBeTruthy();
    expect(data.env_vars.MONGODB_URL).toContain("mongodb://");
    expect(data.env_vars.DATABASE_URL).toBeTruthy();
    expect(data.env_vars.DATABASE_URL).toContain("mongodb://");
  });

  test("disconnect MongoDB removes MONGODB_URL and DATABASE_URL", async ({ request }) => {
    await apiCall(request, "DELETE", `/tenants/${MONGO_TENANT}/apps/${MONGO_APP}/connect-service/${MONGO_SERVICE}`, token);
    const appResp = await apiCall(request, "GET", `/tenants/${MONGO_TENANT}/apps/${MONGO_APP}`, token);
    const env = (await appResp.json()).env_vars || {};
    expect(env.MONGODB_URL).toBeUndefined();
    expect(env.DATABASE_URL).toBeUndefined();
  });

  test("delete MongoDB service", async ({ request }) => {
    const resp = await apiCall(request, "DELETE", `/tenants/${MONGO_TENANT}/services/${MONGO_SERVICE}`, token);
    expect(resp.status()).toBe(204);
  });

  test("verify MongoDB gone", async ({ request }) => {
    const resp = await apiCall(request, "GET", `/tenants/${MONGO_TENANT}/services/${MONGO_SERVICE}`, token);
    expect(resp.status()).toBe(404);
  });
});

// ---------------------------------------------------------------------------
// DB → Credentials → App Env Vars flow (Sprint C1)
// ---------------------------------------------------------------------------
test.describe("DB Credentials to App Env Vars Flow", () => {
  let token: string;
  const TENANT = "testing";
  const APP = "test";
  const DB_NAME = "flow-pg";

  test.beforeAll(async ({ request }) => {
    token = await getApiToken(request);
    await apiCall(request, "DELETE", `/tenants/${TENANT}/services/${DB_NAME}`, token);
  });

  test.afterAll(async ({ request }) => {
    token = await getApiToken(request);
    await apiCall(request, "DELETE", `/tenants/${TENANT}/services/${DB_NAME}`, token);
    // Clear env vars
    await apiCall(request, "PATCH", `/tenants/${TENANT}/apps/${APP}`, token, { env_vars: {} });
  });

  test("create DB and wait for ready", async ({ request }) => {
    const resp = await apiCall(request, "POST", `/tenants/${TENANT}/services`, token, {
      name: DB_NAME,
      service_type: "postgres",
      tier: "dev",
    });
    expect(resp.status()).toBe(201);

    // Poll until ready
    const maxWait = 120_000;
    const start = Date.now();
    let status = "provisioning";
    while (Date.now() - start < maxWait) {
      const r = await apiCall(request, "GET", `/tenants/${TENANT}/services/${DB_NAME}`, token);
      status = (await r.json()).status;
      if (status === "ready" || status === "failed") break;
      await new Promise((r) => setTimeout(r, 5_000));
    }
    expect(status).toBe("ready");
  });

  test("get credentials returns host, user, password", async ({ request }) => {
    const resp = await apiCall(request, "GET", `/tenants/${TENANT}/services/${DB_NAME}/credentials`, token);
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    const keys = Object.keys(data.credentials);
    expect(keys).toContain("host");
    expect(keys).toContain("user");
    expect(keys).toContain("password");
    expect(keys).toContain("port");
  });

  test("user adds DB env vars to app via PATCH", async ({ request }) => {
    // Get credentials first
    const credResp = await apiCall(request, "GET", `/tenants/${TENANT}/services/${DB_NAME}/credentials`, token);
    const creds = (await credResp.json()).credentials;

    // User builds their own env vars from credentials
    const host = creds["pgbouncer-host"] || creds["host"];
    const resp = await apiCall(request, "PATCH", `/tenants/${TENANT}/apps/${APP}`, token, {
      env_vars: {
        DATABASE_URL: `postgresql://${creds.user}:${creds.password}@${host}:${creds.port}/testing_flow_pg`,
        DB_HOST: host,
        DB_PORT: creds.port,
        DB_USER: creds.user,
        DB_NAME: "testing_flow_pg",
      },
    });
    expect(resp.ok()).toBeTruthy();
    const app = await resp.json();
    expect(app.env_vars.DATABASE_URL).toContain("postgresql://");
    expect(app.env_vars.DB_HOST).toBeTruthy();
    expect(app.env_vars.DB_PORT).toBeTruthy();
  });

  test("env vars persist on GET", async ({ request }) => {
    const resp = await apiCall(request, "GET", `/tenants/${TENANT}/apps/${APP}`, token);
    expect(resp.ok()).toBeTruthy();
    const app = await resp.json();
    expect(Object.keys(app.env_vars).length).toBe(5);
    expect(app.env_vars.DATABASE_URL).toContain("postgresql://");
    expect(app.env_vars.DB_HOST).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// Redis Service Lifecycle (CRD-based, Sprint C1.5)
// ---------------------------------------------------------------------------
test.describe("Redis Service Lifecycle", () => {
  let token: string;
  const TENANT = "testing";
  const SVC = "e2e-redis-test";

  test.beforeAll(async ({ request }) => {
    token = await getApiToken(request);
    await apiCall(request, "DELETE", `/tenants/${TENANT}/services/${SVC}`, token);
  });

  test.afterAll(async ({ request }) => {
    token = await getApiToken(request);
    await apiCall(request, "DELETE", `/tenants/${TENANT}/services/${SVC}`, token);
  });

  test("create Redis service", async ({ request }) => {
    const resp = await apiCall(request, "POST", `/tenants/${TENANT}/services`, token, {
      name: SVC, service_type: "redis", tier: "dev",
    });
    expect(resp.status()).toBe(201);
    const data = await resp.json();
    expect(data.service_type).toBe("redis");
    expect(data.status).toBe("provisioning");
    expect(data.connection_hint).toContain("redis://");
  });

  test("poll until Redis is ready", async ({ request }) => {
    const maxWait = 120_000;
    const start = Date.now();
    let status = "provisioning";
    while (Date.now() - start < maxWait) {
      const resp = await apiCall(request, "GET", `/tenants/${TENANT}/services/${SVC}`, token);
      const data = await resp.json();
      status = data.status;
      if (status === "ready" || status === "failed") break;
      await new Promise((r) => setTimeout(r, 5_000));
    }
    expect(status).toBe("ready");
  });

  test("Redis connection_hint has correct format", async ({ request }) => {
    const resp = await apiCall(request, "GET", `/tenants/${TENANT}/services/${SVC}`, token);
    const data = await resp.json();
    expect(data.connection_hint).toMatch(/^redis:\/\/.+:6379$/);
  });

  test("delete Redis service", async ({ request }) => {
    expect((await apiCall(request, "DELETE", `/tenants/${TENANT}/services/${SVC}`, token)).status()).toBe(204);
  });

  test("verify Redis gone", async ({ request }) => {
    expect((await apiCall(request, "GET", `/tenants/${TENANT}/services/${SVC}`, token)).status()).toBe(404);
  });
});

// ---------------------------------------------------------------------------
// RabbitMQ Service Lifecycle (CRD-based, Sprint C1.5)
// ---------------------------------------------------------------------------
test.describe("RabbitMQ Service Lifecycle", () => {
  let token: string;
  const TENANT = "testing";
  const SVC = "e2e-rabbit-test";

  test.beforeAll(async ({ request }) => {
    token = await getApiToken(request);
    await apiCall(request, "DELETE", `/tenants/${TENANT}/services/${SVC}`, token);
  });

  test.afterAll(async ({ request }) => {
    token = await getApiToken(request);
    await apiCall(request, "DELETE", `/tenants/${TENANT}/services/${SVC}`, token);
  });

  test("create RabbitMQ service", async ({ request }) => {
    const resp = await apiCall(request, "POST", `/tenants/${TENANT}/services`, token, {
      name: SVC, service_type: "rabbitmq", tier: "dev",
    });
    expect(resp.status()).toBe(201);
    const data = await resp.json();
    expect(data.service_type).toBe("rabbitmq");
    expect(data.status).toBe("provisioning");
    expect(data.connection_hint).toContain("amqp://");
  });

  test("poll until RabbitMQ is ready", async ({ request }) => {
    const maxWait = 120_000;
    const start = Date.now();
    let status = "provisioning";
    while (Date.now() - start < maxWait) {
      const resp = await apiCall(request, "GET", `/tenants/${TENANT}/services/${SVC}`, token);
      const data = await resp.json();
      status = data.status;
      if (status === "ready" || status === "failed") break;
      await new Promise((r) => setTimeout(r, 5_000));
    }
    expect(status).toBe("ready");
  });

  test("RabbitMQ credentials has username and password", async ({ request }) => {
    const resp = await apiCall(request, "GET", `/tenants/${TENANT}/services/${SVC}/credentials`, token);
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    const keys = Object.keys(data.credentials);
    expect(keys).toContain("username");
    expect(keys).toContain("password");
    expect(keys).toContain("host");
  });

  test("delete RabbitMQ service", async ({ request }) => {
    expect((await apiCall(request, "DELETE", `/tenants/${TENANT}/services/${SVC}`, token)).status()).toBe(204);
  });

  test("verify RabbitMQ gone", async ({ request }) => {
    expect((await apiCall(request, "GET", `/tenants/${TENANT}/services/${SVC}`, token)).status()).toBe(404);
  });
});
