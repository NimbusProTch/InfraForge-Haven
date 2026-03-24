const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
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

// ---- API functions ----

export const api = {
  tenants: {
    list: (token?: string) => apiFetch<Tenant[]>("/tenants", {}, token),
    get: (slug: string, token?: string) =>
      apiFetch<Tenant>(`/tenants/${slug}`, {}, token),
    create: (
      body: { slug: string; name: string },
      token?: string
    ) =>
      apiFetch<Tenant>("/tenants", { method: "POST", body: JSON.stringify(body) }, token),
    delete: (slug: string, token?: string) =>
      apiFetch<void>(`/tenants/${slug}`, { method: "DELETE" }, token),
  },
  apps: {
    list: (tenantSlug: string, token?: string) =>
      apiFetch<Application[]>(`/tenants/${tenantSlug}/apps`, {}, token),
    get: (tenantSlug: string, appSlug: string, token?: string) =>
      apiFetch<Application>(`/tenants/${tenantSlug}/apps/${appSlug}`, {}, token),
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
};
