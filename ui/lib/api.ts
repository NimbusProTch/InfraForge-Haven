const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";
const API_PREFIX = "/api/v1";

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  accessToken?: string
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (accessToken) {
    headers["Authorization"] = `Bearer ${accessToken}`;
  }

  const res = await fetch(`${API_BASE}${API_PREFIX}${path}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`API ${res.status}: ${detail}`);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ---- Types ----

export interface Tenant {
  id: string;
  slug: string;
  name: string;
  namespace: string;
  keycloak_realm: string;
  cpu_limit: string;
  memory_limit: string;
  storage_limit: string;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Application {
  id: string;
  tenant_id: string;
  slug: string;
  name: string;
  repo_url: string;
  branch: string;
  replicas: number;
  image_tag: string | null;
  webhook_token: string;
  created_at: string;
  updated_at: string;
}

export interface ManagedService {
  id: string;
  tenant_id: string;
  name: string;
  service_type: "postgres" | "redis" | "rabbitmq";
  tier: "dev" | "prod";
  status: "provisioning" | "ready" | "failed" | "deleting";
  secret_name: string | null;
  connection_hint: string | null;
  created_at: string;
  updated_at: string;
}

export interface Deployment {
  id: string;
  application_id: string;
  commit_sha: string;
  status: "pending" | "building" | "deploying" | "running" | "failed";
  build_job_name: string | null;
  image_tag: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface ClusterHealth {
  status: "ok" | "degraded";
  kubernetes: {
    status: string;
    [key: string]: unknown;
  };
}

export interface GitHubRepo {
  id: number;
  full_name: string;
  name: string;
  clone_url: string;
  html_url: string;
  default_branch: string;
  private: boolean;
}

export interface GitHubBranch {
  name: string;
  commit: { sha: string };
}

// ---- Logs SSE URL helper ----
export function getLogsUrl(tenantSlug: string, appSlug: string): string {
  return `${API_BASE}${API_PREFIX}/tenants/${tenantSlug}/apps/${appSlug}/logs`;
}

// ---- API functions ----

export const api = {
  health: {
    status: () => apiFetch<{ status: string }>("/health"),
    cluster: () => apiFetch<ClusterHealth>("/health/cluster"),
  },
  tenants: {
    list: (token?: string) => apiFetch<Tenant[]>("/tenants", {}, token),
    get: (slug: string, token?: string) =>
      apiFetch<Tenant>(`/tenants/${slug}`, {}, token),
    create: (body: { slug: string; name: string }, token?: string) =>
      apiFetch<Tenant>("/tenants", { method: "POST", body: JSON.stringify(body) }, token),
    delete: (slug: string, token?: string) =>
      apiFetch<void>(`/tenants/${slug}`, { method: "DELETE" }, token),
  },
  apps: {
    list: (tenantSlug: string, token?: string) =>
      apiFetch<Application[]>(`/tenants/${tenantSlug}/apps`, {}, token),
    get: (tenantSlug: string, appSlug: string, token?: string) =>
      apiFetch<Application>(`/tenants/${tenantSlug}/apps/${appSlug}`, {}, token),
    create: (
      tenantSlug: string,
      body: { slug: string; name: string; repo_url: string; branch: string; replicas?: number },
      token?: string
    ) =>
      apiFetch<Application>(
        `/tenants/${tenantSlug}/apps`,
        { method: "POST", body: JSON.stringify(body) },
        token
      ),
    delete: (tenantSlug: string, appSlug: string, token?: string) =>
      apiFetch<void>(`/tenants/${tenantSlug}/apps/${appSlug}`, { method: "DELETE" }, token),
  },
  deployments: {
    list: (tenantSlug: string, appSlug: string, token?: string) =>
      apiFetch<Deployment[]>(`/tenants/${tenantSlug}/apps/${appSlug}/deployments`, {}, token),
    get: (tenantSlug: string, appSlug: string, deploymentId: string, token?: string) =>
      apiFetch<Deployment>(
        `/tenants/${tenantSlug}/apps/${appSlug}/deployments/${deploymentId}`,
        {},
        token
      ),
    build: (tenantSlug: string, appSlug: string, token?: string) =>
      apiFetch<Deployment>(
        `/tenants/${tenantSlug}/apps/${appSlug}/build`,
        { method: "POST" },
        token
      ),
    deploy: (tenantSlug: string, appSlug: string, token?: string) =>
      apiFetch<Deployment>(
        `/tenants/${tenantSlug}/apps/${appSlug}/deploy`,
        { method: "POST" },
        token
      ),
    rollback: (tenantSlug: string, appSlug: string, deploymentId: string, token?: string) =>
      apiFetch<Deployment>(
        `/tenants/${tenantSlug}/apps/${appSlug}/deployments/${deploymentId}/rollback`,
        { method: "POST" },
        token
      ),
  },
  services: {
    list: (tenantSlug: string, token?: string) =>
      apiFetch<ManagedService[]>(`/tenants/${tenantSlug}/services`, {}, token),
    create: (
      tenantSlug: string,
      body: { name: string; service_type: string; tier: string },
      token?: string
    ) =>
      apiFetch<ManagedService>(
        `/tenants/${tenantSlug}/services`,
        { method: "POST", body: JSON.stringify(body) },
        token
      ),
    delete: (tenantSlug: string, serviceName: string, token?: string) =>
      apiFetch<void>(
        `/tenants/${tenantSlug}/services/${serviceName}`,
        { method: "DELETE" },
        token
      ),
  },
  github: {
    authUrl: () => apiFetch<{ url: string; state: string }>("/github/auth/url"),
    repos: (token: string) =>
      apiFetch<GitHubRepo[]>("/github/repos", {}, token),
    branches: (owner: string, repo: string, token: string) =>
      apiFetch<GitHubBranch[]>(`/github/repos/${owner}/${repo}/branches`, {}, token),
  },
};
