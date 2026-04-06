/**
 * Playwright test helpers — API mocking, auth bypass, test data factories.
 */
import { type Page, type Route } from "@playwright/test";
import { EncryptJWT } from "jose";
import { hkdf } from "@panva/hkdf";

const API_BASE = "http://localhost:8000/api/v1";
const NEXTAUTH_SECRET = "test-secret-for-playwright-e2e-testing-only";

// ---------------------------------------------------------------------------
// Auth bypass — mock NextAuth session (middleware + client-side)
// ---------------------------------------------------------------------------

/** Derive the next-auth encryption key from the secret */
async function deriveKey(): Promise<Uint8Array> {
  return new Uint8Array(
    await hkdf("sha256", NEXTAUTH_SECRET, "", "NextAuth.js Generated Encryption Key", 32)
  );
}

/** Create an encrypted JWT session token that next-auth middleware accepts */
async function createSessionToken(): Promise<string> {
  const key = await deriveKey();
  return new EncryptJWT({
    name: "Test User",
    email: "test@haven.nl",
    accessToken: "mock-jwt-token",
    refreshToken: "mock-refresh",
    expiresAt: Math.floor(Date.now() / 1000) + 86400,
    provider: "keycloak",
    sub: "test-user-id",
  })
    .setProtectedHeader({ alg: "dir", enc: "A256GCM" })
    .setIssuedAt()
    .setExpirationTime("24h")
    .setJti("test-jti")
    .encrypt(key);
}

export async function mockSession(page: Page) {
  // Set the session cookie so next-auth middleware allows access
  const token = await createSessionToken();
  await page.context().addCookies([
    {
      name: "next-auth.session-token",
      value: token,
      domain: "localhost",
      path: "/",
      httpOnly: true,
      sameSite: "Lax",
      expires: Math.floor(Date.now() / 1000) + 86400,
    },
  ]);

  // Mock the NextAuth session endpoint (client-side useSession)
  await page.route("**/api/auth/session", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        user: {
          name: "Test User",
          email: "test@haven.nl",
          image: null,
        },
        expires: "2099-12-31T23:59:59.999Z",
        accessToken: "mock-jwt-token",
        provider: "keycloak",
      }),
    })
  );

  // Mock CSRF token
  await page.route("**/api/auth/csrf", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ csrfToken: "mock-csrf-token" }),
    })
  );

  // Mock providers
  await page.route("**/api/auth/providers", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        keycloak: {
          id: "keycloak",
          name: "Keycloak",
          type: "oauth",
          signinUrl: "/api/auth/signin/keycloak",
        },
      }),
    })
  );
}

// ---------------------------------------------------------------------------
// API mock helpers
// ---------------------------------------------------------------------------

export function apiUrl(path: string) {
  return `**${API_BASE}${path}`;
}

/** Mock a GET endpoint that returns JSON */
export async function mockGet(page: Page, path: string, data: unknown) {
  await page.route(apiUrl(path), (route) => {
    if (route.request().method() === "GET") {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(data) });
    } else {
      route.continue();
    }
  });
}

/** Mock a POST endpoint that returns JSON */
export async function mockPost(page: Page, path: string, data: unknown, status = 201) {
  await page.route(apiUrl(path), (route) => {
    if (route.request().method() === "POST") {
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(data) });
    } else {
      route.continue();
    }
  });
}

/** Mock any method on a path */
export async function mockApi(
  page: Page,
  path: string,
  handler: (route: Route) => void
) {
  await page.route(apiUrl(path), handler);
}

// ---------------------------------------------------------------------------
// Test data factories
// ---------------------------------------------------------------------------

export const TENANT = {
  id: "t-001",
  slug: "gemeente-test",
  name: "Gemeente Test",
  namespace: "tenant-gemeente-test",
  keycloak_realm: "gemeente-test",
  tier: "free",
  github_connected: false,
  cpu_limit: "16",
  memory_limit: "32Gi",
  storage_limit: "100Gi",
  active: true,
  created_at: "2026-04-01T10:00:00Z",
  updated_at: "2026-04-01T10:00:00Z",
};

export const APP = {
  id: "a-001",
  tenant_id: "t-001",
  slug: "test-api",
  name: "Test API",
  repo_url: "https://github.com/test/repo",
  branch: "main",
  env_vars: {},
  image_tag: "harbor.example.com/haven/test:abc123",
  replicas: 2,
  port: 8080,
  webhook_token: "wh-token",
  dockerfile_path: null,
  build_context: null,
  use_dockerfile: false,
  detected_deps: null,
  custom_domain: null,
  health_check_path: "/health",
  resource_cpu_request: "50m",
  resource_cpu_limit: "500m",
  resource_memory_request: "64Mi",
  resource_memory_limit: "512Mi",
  min_replicas: 1,
  max_replicas: 5,
  cpu_threshold: 70,
  auto_deploy: true,
  app_type: "web",
  canary_enabled: false,
  canary_weight: 10,
  volumes: null,
  env_from_secrets: [],
  created_at: "2026-04-01T10:00:00Z",
  updated_at: "2026-04-01T10:00:00Z",
};

export const SERVICE_PG = {
  id: "s-001",
  tenant_id: "t-001",
  name: "app-pg",
  service_type: "postgres",
  tier: "dev",
  status: "ready",
  secret_name: "svc-app-pg",
  service_namespace: "everest",
  connection_hint: "postgresql://user@host:5432/db",
  error_message: null,
  everest_name: "gemeente-test-app-pg",
  db_name: "postgres",
  db_user: "postgres",
  credentials_provisioned: true,
  created_at: "2026-04-01T10:00:00Z",
  updated_at: "2026-04-01T10:00:00Z",
};

export const SERVICE_REDIS = {
  ...SERVICE_PG,
  id: "s-002",
  name: "app-redis",
  service_type: "redis",
  connection_hint: "redis://app-redis.tenant-gemeente-test.svc:6379",
  everest_name: null,
};

export const DEPLOYMENT = {
  id: "d-001",
  application_id: "a-001",
  commit_sha: "abc12345",
  status: "running",
  build_job_name: "build-test-api-abc123",
  image_tag: "harbor.example.com/haven/test:abc123",
  error_message: null,
  created_at: "2026-04-01T12:00:00Z",
  updated_at: "2026-04-01T12:05:00Z",
};

export const MEMBER = {
  id: "m-001",
  tenant_id: "t-001",
  user_id: "user-001",
  email: "admin@gemeente-test.nl",
  display_name: "Admin User",
  role: "owner",
  created_at: "2026-04-01T10:00:00Z",
  updated_at: "2026-04-01T10:00:00Z",
};

export const CLUSTER_HEALTH = {
  status: "ok",
  k8s_available: true,
  db_available: true,
};

export const PODS = {
  k8s_available: true,
  pods: [
    {
      name: "test-api-abc-123",
      status: "Running",
      restart_count: 0,
      age: "2h",
      node: "worker-1",
      cpu: "50m",
      memory: "128Mi",
      cpu_percent: 10,
      memory_percent: 25,
    },
  ],
};

export const EVENTS = {
  k8s_available: true,
  events: [
    {
      object_name: "test-api-abc-123",
      reason: "Pulled",
      message: "Successfully pulled image",
      count: 1,
      first_seen: "2026-04-01T12:00:00Z",
      last_seen: "2026-04-01T12:00:00Z",
    },
  ],
};

export const BACKUP_LIST = {
  tenant_slug: "gemeente-test",
  service_name: "app-pg",
  k8s_available: true,
  backups: [
    {
      backup_id: "backup-app-pg-20260401",
      service_name: "gemeente-test-app-pg",
      service_type: "postgres",
      phase: "Succeeded",
      started_at: "2026-04-01T02:00:00Z",
      finished_at: "2026-04-01T02:05:00Z",
      size: null,
      s3_path: "s3://haven-backups/gemeente-test/postgres",
    },
  ],
};
