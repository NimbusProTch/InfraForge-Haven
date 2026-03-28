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

// Members
export interface TenantMember {
  id: string;
  tenant_id: string;
  user_id: string;
  email: string;
  role: "admin" | "developer" | "viewer";
  created_at: string;
  updated_at: string;
}

// Environments
export interface Environment {
  id: string;
  application_id: string;
  name: string;
  type: "staging" | "preview" | "production";
  branch: string | null;
  url: string | null;
  status: "active" | "inactive" | "building";
  created_at: string;
  updated_at: string;
}

// Domains
export interface Domain {
  id: string;
  application_id: string;
  domain: string;
  verified: boolean;
  tls_enabled: boolean;
  cert_status: string | null;
  created_at: string;
  updated_at: string;
}

export interface DomainVerifyResult {
  domain: string;
  verified: boolean;
  dns_records: Array<{ type: string; name: string; value: string }>;
}

// Audit
export interface AuditLog {
  id: string;
  tenant_id: string;
  user_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  detail: Record<string, unknown> | null;
  created_at: string;
}

export interface AuditLogList {
  items: AuditLog[];
  total: number;
  page: number;
  page_size: number;
}

// Billing
export interface UsageSummary {
  tier: string;
  limits: Record<string, number>;
  current_period: Record<string, unknown>;
  usage_pct: Record<string, number>;
  history: Array<Record<string, unknown>>;
}

// GDPR
export interface Consent {
  id: string;
  tenant_id: string;
  consent_type: string;
  granted: boolean;
  granted_at: string | null;
  revoked_at: string | null;
}

export interface RetentionPolicy {
  tenant_id: string;
  log_retention_days: number;
  backup_retention_days: number;
  updated_at: string;
}

export interface DataExport {
  export_id: string;
  status: string;
  download_url: string | null;
  expires_at: string | null;
}

export interface ErasureResult {
  status: string;
  erased_resources: string[];
}

// Organizations
export interface Organization {
  id: string;
  slug: string;
  name: string;
  created_at: string;
  updated_at: string;
}

export interface OrgMember {
  id: string;
  org_id: string;
  user_id: string;
  email: string;
  role: string;
  created_at: string;
}

export interface SSOConfig {
  id: string;
  org_id: string;
  provider: string;
  client_id: string;
  enabled: boolean;
  created_at: string;
}

export interface OrgTenant {
  id: string;
  org_id: string;
  tenant_id: string;
  created_at: string;
}

export interface BillingSummary {
  org_id: string;
  total_tenants: number;
  total_usage: Record<string, number>;
}

// Backup
export interface BackupItem {
  id: string;
  tenant_id: string;
  resource_type: string;
  status: "pending" | "in_progress" | "completed" | "failed";
  created_at: string;
  completed_at: string | null;
  size_bytes: number | null;
}

export interface BackupList {
  items: BackupItem[];
  total: number;
}

export interface BackupTriggerResult {
  backup_id: string;
  status: string;
}

// Canary
export interface CanaryStatus {
  enabled: boolean;
  canary_weight: number;
  stable_image: string | null;
  canary_image: string | null;
  created_at: string | null;
  updated_at: string | null;
}

// CronJobs
export interface CronJob {
  id: string;
  application_id: string;
  name: string;
  schedule: string;
  command: string;
  enabled: boolean;
  last_run_at: string | null;
  last_run_status: string | null;
  created_at: string;
  updated_at: string;
}

// PVCs / Volumes
export interface VolumeItem {
  name: string;
  size_gi: number;
  access_mode: string;
  status: string;
  storage_class: string | null;
  created_at: string | null;
}

export interface VolumeList {
  volumes: VolumeItem[];
  k8s_available: boolean;
}

// Clusters
export interface Cluster {
  id: string;
  name: string;
  region: string;
  provider: string;
  endpoint: string | null;
  status: "active" | "inactive" | "degraded" | "unknown";
  is_primary: boolean;
  created_at: string;
  updated_at: string;
}

export interface ClusterHealthResponse {
  cluster_id: string;
  status: string;
  checked_at: string;
  details: Record<string, unknown>;
}

export interface MultiRegionRoutingResponse {
  clusters: Array<{ cluster_id: string; region: string; weight: number }>;
  strategy: string;
}

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
  port: number;
  image_tag: string | null;
  webhook_token: string;
  env_vars: Record<string, string>;
  // Monorepo
  dockerfile_path: string | null;
  build_context: string | null;
  use_dockerfile: boolean;
  detected_deps: DetectedDeps | null;
  // Production hardening
  custom_domain: string | null;
  health_check_path: string | null;
  resource_cpu_request: string;
  resource_cpu_limit: string;
  resource_memory_request: string;
  resource_memory_limit: string;
  min_replicas: number;
  max_replicas: number;
  cpu_threshold: number;
  auto_deploy: boolean;
  created_at: string;
  updated_at: string;
}

export interface DetectedDeps {
  language: string;
  framework: string | null;
  databases: string[];
  caches: string[];
  queues: string[];
  has_dockerfile: boolean;
  suggested_services: Array<{ type: string; reason: string }>;
}

export interface ManagedService {
  id: string;
  tenant_id: string;
  name: string;
  service_type: "postgres" | "mysql" | "mongodb" | "redis" | "rabbitmq";
  tier: "dev" | "prod";
  status: "provisioning" | "ready" | "failed" | "deleting";
  secret_name: string | null;
  connection_hint: string | null;
  created_at: string;
  updated_at: string;
}

export interface RepoTreeItem {
  path: string;
  type: "blob" | "tree";
  size: number | null;
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

export interface PodInfo {
  name: string;
  status: string;
  restarts: number;
  age: string;
  cpu_value: string | null;
  memory_value: string | null;
  cpu_usage: number | null;
  memory_usage: number | null;
  node: string | null;
}

export interface PodsResponse {
  pods: PodInfo[];
  k8s_available: boolean;
}

export interface AppEvent {
  reason: string;
  message: string;
  type: string;
  count: number;
  first_time: string | null;
  last_time: string | null;
  object_name: string;
}

export interface EventsResponse {
  events: AppEvent[];
  k8s_available: boolean;
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
export function getLogsUrl(tenantSlug: string, appSlug: string, token?: string): string {
  const base = `${API_BASE}${API_PREFIX}/tenants/${tenantSlug}/apps/${appSlug}/logs`;
  if (token) {
    return `${base}?token=${encodeURIComponent(token)}`;
  }
  return base;
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
      body: Partial<Application> & { name: string; repo_url: string },
      token?: string
    ) =>
      apiFetch<Application>(
        `/tenants/${tenantSlug}/apps`,
        { method: "POST", body: JSON.stringify(body) },
        token
      ),
    update: (
      tenantSlug: string,
      appSlug: string,
      body: Partial<Application>,
      token?: string
    ) =>
      apiFetch<Application>(
        `/tenants/${tenantSlug}/apps/${appSlug}`,
        { method: "PATCH", body: JSON.stringify(body) },
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
  observability: {
    pods: (tenantSlug: string, appSlug: string, token?: string) =>
      apiFetch<PodsResponse>(`/tenants/${tenantSlug}/apps/${appSlug}/pods`, {}, token),
    events: (tenantSlug: string, appSlug: string, token?: string) =>
      apiFetch<EventsResponse>(`/tenants/${tenantSlug}/apps/${appSlug}/events`, {}, token),
  },
  github: {
    authUrl: () => apiFetch<{ url: string; state: string }>("/github/auth/url"),
    repos: (token: string) =>
      apiFetch<GitHubRepo[]>("/github/repos", {}, token),
    branches: (owner: string, repo: string, token: string) =>
      apiFetch<GitHubBranch[]>(`/github/repos/${owner}/${repo}/branches`, {}, token),
    /** Store the GitHub OAuth token server-side for a tenant (used for builds). */
    connect: (tenantSlug: string, githubToken: string, accessToken?: string) =>
      apiFetch<{ status: string; tenant_slug: string }>(
        `/github/connect/${tenantSlug}`,
        { method: "POST", body: JSON.stringify({ access_token: githubToken }) },
        accessToken
      ),
    /** Remove the stored GitHub token for a tenant. */
    disconnect: (tenantSlug: string, accessToken?: string) =>
      apiFetch<{ status: string; tenant_slug: string }>(
        `/github/connect/${tenantSlug}`,
        { method: "DELETE" },
        accessToken
      ),
    /** List files in a repository (monorepo support) */
    tree: (owner: string, repo: string, ref: string, token: string) =>
      apiFetch<RepoTreeItem[]>(`/github/repos/${owner}/${repo}/tree?ref=${ref}`, {}, token),
    /** Detect dependencies for a repository */
    detect: (owner: string, repo: string, ref: string, token: string) =>
      apiFetch<DetectedDeps>(`/github/repos/${owner}/${repo}/detect?ref=${ref}`, {}, token),
  },
  members: {
    list: (tenantSlug: string, token?: string) =>
      apiFetch<TenantMember[]>(`/tenants/${tenantSlug}/members`, {}, token),
    add: (tenantSlug: string, body: { email: string; role: string }, token?: string) =>
      apiFetch<TenantMember>(
        `/tenants/${tenantSlug}/members`,
        { method: "POST", body: JSON.stringify(body) },
        token
      ),
    update: (tenantSlug: string, userId: string, body: { role: string }, token?: string) =>
      apiFetch<TenantMember>(
        `/tenants/${tenantSlug}/members/${userId}`,
        { method: "PATCH", body: JSON.stringify(body) },
        token
      ),
    remove: (tenantSlug: string, userId: string, token?: string) =>
      apiFetch<void>(`/tenants/${tenantSlug}/members/${userId}`, { method: "DELETE" }, token),
  },
  environments: {
    list: (tenantSlug: string, appSlug: string, token?: string) =>
      apiFetch<Environment[]>(`/tenants/${tenantSlug}/apps/${appSlug}/environments`, {}, token),
    create: (
      tenantSlug: string,
      appSlug: string,
      body: { name: string; type: string; branch?: string },
      token?: string
    ) =>
      apiFetch<Environment>(
        `/tenants/${tenantSlug}/apps/${appSlug}/environments`,
        { method: "POST", body: JSON.stringify(body) },
        token
      ),
    get: (tenantSlug: string, appSlug: string, envName: string, token?: string) =>
      apiFetch<Environment>(
        `/tenants/${tenantSlug}/apps/${appSlug}/environments/${envName}`,
        {},
        token
      ),
    update: (
      tenantSlug: string,
      appSlug: string,
      envName: string,
      body: Partial<Environment>,
      token?: string
    ) =>
      apiFetch<Environment>(
        `/tenants/${tenantSlug}/apps/${appSlug}/environments/${envName}`,
        { method: "PATCH", body: JSON.stringify(body) },
        token
      ),
    delete: (tenantSlug: string, appSlug: string, envName: string, token?: string) =>
      apiFetch<void>(
        `/tenants/${tenantSlug}/apps/${appSlug}/environments/${envName}`,
        { method: "DELETE" },
        token
      ),
  },
  domains: {
    list: (tenantSlug: string, appSlug: string, token?: string) =>
      apiFetch<Domain[]>(`/tenants/${tenantSlug}/apps/${appSlug}/domains`, {}, token),
    add: (tenantSlug: string, appSlug: string, body: { domain: string }, token?: string) =>
      apiFetch<Domain>(
        `/tenants/${tenantSlug}/apps/${appSlug}/domains`,
        { method: "POST", body: JSON.stringify(body) },
        token
      ),
    get: (tenantSlug: string, appSlug: string, domain: string, token?: string) =>
      apiFetch<Domain>(`/tenants/${tenantSlug}/apps/${appSlug}/domains/${domain}`, {}, token),
    verify: (tenantSlug: string, appSlug: string, domain: string, token?: string) =>
      apiFetch<DomainVerifyResult>(
        `/tenants/${tenantSlug}/apps/${appSlug}/domains/${domain}/verify`,
        { method: "POST" },
        token
      ),
    syncCert: (tenantSlug: string, appSlug: string, domain: string, token?: string) =>
      apiFetch<Domain>(
        `/tenants/${tenantSlug}/apps/${appSlug}/domains/${domain}/sync-cert`,
        { method: "POST" },
        token
      ),
    delete: (tenantSlug: string, appSlug: string, domain: string, token?: string) =>
      apiFetch<void>(
        `/tenants/${tenantSlug}/apps/${appSlug}/domains/${domain}`,
        { method: "DELETE" },
        token
      ),
    wildcardCert: (body: { domain: string }, token?: string) =>
      apiFetch<Record<string, unknown>>(
        "/platform/domains/wildcard-cert",
        { method: "POST", body: JSON.stringify(body) },
        token
      ),
  },
  audit: {
    list: (
      tenantSlug: string,
      params: { page?: number; page_size?: number; action?: string; resource_type?: string } = {},
      token?: string
    ) => {
      const qs = new URLSearchParams(
        Object.entries(params)
          .filter(([, v]) => v !== undefined)
          .map(([k, v]) => [k, String(v)])
      ).toString();
      return apiFetch<AuditLogList>(
        `/tenants/${tenantSlug}/audit-logs${qs ? `?${qs}` : ""}`,
        {},
        token
      );
    },
  },
  billing: {
    usage: (tenantSlug: string, historyMonths?: number, token?: string) => {
      const qs = historyMonths !== undefined ? `?history_months=${historyMonths}` : "";
      return apiFetch<UsageSummary>(`/tenants/${tenantSlug}/usage${qs}`, {}, token);
    },
    updateTier: (tenantSlug: string, tier: string, token?: string) =>
      apiFetch<{ slug: string; tier: string }>(
        `/tenants/${tenantSlug}/tier?tier=${encodeURIComponent(tier)}`,
        { method: "PATCH" },
        token
      ),
  },
  gdpr: {
    listConsents: (tenantSlug: string, token?: string) =>
      apiFetch<Consent[]>(`/tenants/${tenantSlug}/gdpr/consent`, {}, token),
    grantConsent: (
      tenantSlug: string,
      body: { consent_type: string },
      token?: string
    ) =>
      apiFetch<Consent>(
        `/tenants/${tenantSlug}/gdpr/consent`,
        { method: "POST", body: JSON.stringify(body) },
        token
      ),
    revokeConsent: (tenantSlug: string, consentType: string, token?: string) =>
      apiFetch<Consent>(
        `/tenants/${tenantSlug}/gdpr/consent/${consentType}`,
        { method: "DELETE" },
        token
      ),
    getRetention: (tenantSlug: string, token?: string) =>
      apiFetch<RetentionPolicy>(`/tenants/${tenantSlug}/gdpr/retention`, {}, token),
    updateRetention: (
      tenantSlug: string,
      body: Partial<RetentionPolicy>,
      token?: string
    ) =>
      apiFetch<RetentionPolicy>(
        `/tenants/${tenantSlug}/gdpr/retention`,
        { method: "PATCH", body: JSON.stringify(body) },
        token
      ),
    export: (tenantSlug: string, token?: string) =>
      apiFetch<DataExport>(`/tenants/${tenantSlug}/gdpr/export`, {}, token),
    erase: (tenantSlug: string, token?: string) =>
      apiFetch<ErasureResult>(
        `/tenants/${tenantSlug}/gdpr/erase`,
        { method: "POST" },
        token
      ),
  },
  organizations: {
    list: (token?: string) => apiFetch<Organization[]>("/organizations", {}, token),
    create: (body: { slug: string; name: string }, token?: string) =>
      apiFetch<Organization>(
        "/organizations",
        { method: "POST", body: JSON.stringify(body) },
        token
      ),
    get: (orgSlug: string, token?: string) =>
      apiFetch<Organization>(`/organizations/${orgSlug}`, {}, token),
    update: (orgSlug: string, body: Partial<Organization>, token?: string) =>
      apiFetch<Organization>(
        `/organizations/${orgSlug}`,
        { method: "PATCH", body: JSON.stringify(body) },
        token
      ),
    delete: (orgSlug: string, token?: string) =>
      apiFetch<void>(`/organizations/${orgSlug}`, { method: "DELETE" }, token),
    listMembers: (orgSlug: string, token?: string) =>
      apiFetch<OrgMember[]>(`/organizations/${orgSlug}/members`, {}, token),
    addMember: (orgSlug: string, body: { email: string; role: string }, token?: string) =>
      apiFetch<OrgMember>(
        `/organizations/${orgSlug}/members`,
        { method: "POST", body: JSON.stringify(body) },
        token
      ),
    updateMember: (orgSlug: string, userId: string, body: { role: string }, token?: string) =>
      apiFetch<OrgMember>(
        `/organizations/${orgSlug}/members/${userId}`,
        { method: "PATCH", body: JSON.stringify(body) },
        token
      ),
    removeMember: (orgSlug: string, userId: string, token?: string) =>
      apiFetch<void>(
        `/organizations/${orgSlug}/members/${userId}`,
        { method: "DELETE" },
        token
      ),
    listSSO: (orgSlug: string, token?: string) =>
      apiFetch<SSOConfig[]>(`/organizations/${orgSlug}/sso`, {}, token),
    createSSO: (
      orgSlug: string,
      body: { provider: string; client_id: string; client_secret: string },
      token?: string
    ) =>
      apiFetch<SSOConfig>(
        `/organizations/${orgSlug}/sso`,
        { method: "POST", body: JSON.stringify(body) },
        token
      ),
    updateSSO: (orgSlug: string, ssoId: string, body: Partial<SSOConfig>, token?: string) =>
      apiFetch<SSOConfig>(
        `/organizations/${orgSlug}/sso/${ssoId}`,
        { method: "PATCH", body: JSON.stringify(body) },
        token
      ),
    deleteSSO: (orgSlug: string, ssoId: string, token?: string) =>
      apiFetch<void>(`/organizations/${orgSlug}/sso/${ssoId}`, { method: "DELETE" }, token),
    listTenants: (orgSlug: string, token?: string) =>
      apiFetch<OrgTenant[]>(`/organizations/${orgSlug}/tenants`, {}, token),
    bindTenant: (orgSlug: string, body: { tenant_id: string }, token?: string) =>
      apiFetch<OrgTenant>(
        `/organizations/${orgSlug}/tenants`,
        { method: "POST", body: JSON.stringify(body) },
        token
      ),
    unbindTenant: (orgSlug: string, tenantId: string, token?: string) =>
      apiFetch<void>(
        `/organizations/${orgSlug}/tenants/${tenantId}`,
        { method: "DELETE" },
        token
      ),
    billingSummary: (orgSlug: string, token?: string) =>
      apiFetch<BillingSummary>(`/organizations/${orgSlug}/billing`, {}, token),
  },
  backup: {
    list: (tenantSlug: string, token?: string) =>
      apiFetch<BackupList>(`/tenants/${tenantSlug}/backup`, {}, token),
    trigger: (tenantSlug: string, body: { resource_type: string }, token?: string) =>
      apiFetch<BackupTriggerResult>(
        `/tenants/${tenantSlug}/backup`,
        { method: "POST", body: JSON.stringify(body) },
        token
      ),
    setSchedule: (
      tenantSlug: string,
      body: { schedule: string; enabled: boolean },
      token?: string
    ) =>
      apiFetch<void>(
        `/tenants/${tenantSlug}/backup/schedule`,
        { method: "PUT", body: JSON.stringify(body) },
        token
      ),
  },
  canary: {
    status: (tenantSlug: string, appSlug: string, token?: string) =>
      apiFetch<CanaryStatus>(
        `/tenants/${tenantSlug}/apps/${appSlug}/canary`,
        {},
        token
      ),
    set: (
      tenantSlug: string,
      appSlug: string,
      body: { enabled: boolean; canary_weight?: number; canary_image?: string },
      token?: string
    ) =>
      apiFetch<CanaryStatus>(
        `/tenants/${tenantSlug}/apps/${appSlug}/canary`,
        { method: "PUT", body: JSON.stringify(body) },
        token
      ),
    promote: (tenantSlug: string, appSlug: string, token?: string) =>
      apiFetch<void>(
        `/tenants/${tenantSlug}/apps/${appSlug}/canary/promote`,
        { method: "POST" },
        token
      ),
    rollback: (tenantSlug: string, appSlug: string, token?: string) =>
      apiFetch<void>(
        `/tenants/${tenantSlug}/apps/${appSlug}/canary/rollback`,
        { method: "POST" },
        token
      ),
  },
  cronjobs: {
    list: (tenantSlug: string, appSlug: string, token?: string) =>
      apiFetch<CronJob[]>(`/tenants/${tenantSlug}/apps/${appSlug}/cronjobs`, {}, token),
    create: (
      tenantSlug: string,
      appSlug: string,
      body: { name: string; schedule: string; command: string },
      token?: string
    ) =>
      apiFetch<CronJob>(
        `/tenants/${tenantSlug}/apps/${appSlug}/cronjobs`,
        { method: "POST", body: JSON.stringify(body) },
        token
      ),
    get: (tenantSlug: string, appSlug: string, cronjobId: string, token?: string) =>
      apiFetch<CronJob>(
        `/tenants/${tenantSlug}/apps/${appSlug}/cronjobs/${cronjobId}`,
        {},
        token
      ),
    update: (
      tenantSlug: string,
      appSlug: string,
      cronjobId: string,
      body: Partial<CronJob>,
      token?: string
    ) =>
      apiFetch<CronJob>(
        `/tenants/${tenantSlug}/apps/${appSlug}/cronjobs/${cronjobId}`,
        { method: "PATCH", body: JSON.stringify(body) },
        token
      ),
    delete: (tenantSlug: string, appSlug: string, cronjobId: string, token?: string) =>
      apiFetch<void>(
        `/tenants/${tenantSlug}/apps/${appSlug}/cronjobs/${cronjobId}`,
        { method: "DELETE" },
        token
      ),
    runNow: (tenantSlug: string, appSlug: string, cronjobId: string, token?: string) =>
      apiFetch<void>(
        `/tenants/${tenantSlug}/apps/${appSlug}/cronjobs/${cronjobId}/run`,
        { method: "POST" },
        token
      ),
  },
  pvcs: {
    list: (tenantSlug: string, appSlug: string, token?: string) =>
      apiFetch<VolumeList>(`/tenants/${tenantSlug}/apps/${appSlug}/volumes`, {}, token),
    create: (
      tenantSlug: string,
      appSlug: string,
      body: { name: string; size_gi: number; access_mode?: string },
      token?: string
    ) =>
      apiFetch<VolumeItem>(
        `/tenants/${tenantSlug}/apps/${appSlug}/volumes`,
        { method: "POST", body: JSON.stringify(body) },
        token
      ),
    delete: (tenantSlug: string, appSlug: string, volumeName: string, token?: string) =>
      apiFetch<void>(
        `/tenants/${tenantSlug}/apps/${appSlug}/volumes/${volumeName}`,
        { method: "DELETE" },
        token
      ),
  },
  clusters: {
    list: (token?: string) => apiFetch<Cluster[]>("/clusters", {}, token),
    create: (body: { name: string; region: string; provider: string; endpoint?: string }, token?: string) =>
      apiFetch<Cluster>("/clusters", { method: "POST", body: JSON.stringify(body) }, token),
    get: (clusterId: string, token?: string) =>
      apiFetch<Cluster>(`/clusters/${clusterId}`, {}, token),
    update: (clusterId: string, body: Partial<Cluster>, token?: string) =>
      apiFetch<Cluster>(
        `/clusters/${clusterId}`,
        { method: "PATCH", body: JSON.stringify(body) },
        token
      ),
    delete: (clusterId: string, token?: string) =>
      apiFetch<void>(`/clusters/${clusterId}`, { method: "DELETE" }, token),
    healthCheck: (clusterId: string, token?: string) =>
      apiFetch<ClusterHealthResponse>(
        `/clusters/${clusterId}/health-check`,
        { method: "POST" },
        token
      ),
    healthCheckAll: (token?: string) =>
      apiFetch<ClusterHealthResponse[]>("/clusters/health-check/all", { method: "POST" }, token),
    failover: (clusterId: string, token?: string) =>
      apiFetch<Cluster | null>(
        `/clusters/${clusterId}/failover`,
        { method: "POST" },
        token
      ),
    routingTable: (token?: string) =>
      apiFetch<MultiRegionRoutingResponse>("/clusters/routing/table", {}, token),
    routingByRegion: (region: string, token?: string) =>
      apiFetch<Cluster | null>(`/clusters/routing/region/${region}`, {}, token),
  },
};
