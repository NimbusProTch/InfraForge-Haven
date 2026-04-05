"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { useRouter, useParams } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/ui/badge";
import { Breadcrumb } from "@/components/Breadcrumb";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { AddServiceModal } from "@/components/AddServiceModal";
import { ModifyServiceModal } from "@/components/ModifyServiceModal";
import { ServiceIcon } from "@/components/icons/ServiceIcons";
import MembersTab from "@/components/MembersTab";
import BillingTab from "@/components/BillingTab";
import AuditLogsTab from "@/components/AuditLogsTab";
import GdprTab from "@/components/GdprTab";
import { useToast } from "@/components/Toast";
import { api, type Tenant, type Application, type ManagedService, type ServiceCredentials, type Deployment } from "@/lib/api";
import {
  ArrowRight,
  Plus,
  Box,
  Database,
  Loader2,
  GitBranch,
  Server,
  Copy,
  Check,
  Trash2,
  ExternalLink,
  Clock,
  Activity,
  FolderKanban,
  Key,
  Link2,
  Unlink,
  Eye,
  EyeOff,
  X,
  Users,
  BarChart3,
  FileText,
  Shield,
  Settings,
} from "lucide-react";

const LB_IP = process.env.NEXT_PUBLIC_LB_IP ?? "";

function appUrl(tenantSlug: string, appSlug: string) {
  if (!LB_IP) return null;
  return `https://${appSlug}.${tenantSlug}.apps.${LB_IP}.sslip.io`;
}

const SERVICE_STATUS_VARIANT: Record<string, "success" | "warning" | "destructive" | "secondary"> = {
  ready: "success",
  provisioning: "warning",
  failed: "destructive",
  deleting: "secondary",
};

const DEPLOY_STATUS_VARIANT: Record<string, "success" | "warning" | "destructive" | "secondary" | "default"> = {
  running: "success",
  building: "warning",
  deploying: "warning",
  pending: "secondary",
  failed: "destructive",
};

const STATUS_DOT: Record<string, string> = {
  running: "bg-emerald-500",
  building: "bg-amber-500 animate-pulse",
  deploying: "bg-blue-500 animate-pulse",
  pending: "bg-zinc-500",
  failed: "bg-red-500",
};

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      className="text-gray-400 dark:text-zinc-600 hover:text-gray-700 dark:hover:text-zinc-300 transition-colors"
    >
      {copied ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
    </button>
  );
}

function AppCard({
  app,
  tenantSlug,
  latestDeployment,
}: {
  app: Application;
  tenantSlug: string;
  latestDeployment?: Deployment;
}) {
  const url = appUrl(tenantSlug, app.slug);
  const deployStatus = latestDeployment?.status;

  return (
    <div className="bg-white dark:bg-zinc-900/50 border border-gray-200 dark:border-zinc-800 rounded-xl p-4 hover:border-gray-300 dark:hover:border-zinc-700 transition-colors group shadow-sm">
      <div className="flex items-start justify-between mb-3">
        <Link href={`/tenants/${tenantSlug}/apps/${app.slug}`} className="flex items-center gap-2.5 flex-1 min-w-0">
          <div className="relative shrink-0">
            <div className="w-8 h-8 rounded-lg bg-gray-100 dark:bg-zinc-800 flex items-center justify-center">
              <Server className="w-4 h-4 text-gray-500 dark:text-zinc-500" />
            </div>
            {deployStatus && (
              <span
                className={`absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-white dark:border-zinc-900 ${STATUS_DOT[deployStatus] ?? "bg-zinc-500"}`}
              />
            )}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-medium text-gray-800 dark:text-zinc-200 group-hover:text-gray-900 dark:group-hover:text-zinc-100 transition-colors truncate">
              {app.name}
            </p>
            <p className="text-xs text-gray-400 dark:text-zinc-600 font-mono mt-0.5 truncate">
              {app.slug}
            </p>
          </div>
        </Link>
        {deployStatus && (
          <Badge variant={DEPLOY_STATUS_VARIANT[deployStatus] ?? "secondary"}>
            {deployStatus}
          </Badge>
        )}
      </div>

      <div className="flex items-center gap-3 text-xs text-gray-400 dark:text-zinc-600">
        <span className="flex items-center gap-1">
          <GitBranch className="w-3 h-3" />
          {app.branch}
        </span>
        <span className="flex items-center gap-1">
          <Activity className="w-3 h-3" />
          {app.replicas} replica{app.replicas !== 1 ? "s" : ""}
        </span>
        {latestDeployment && (
          <span className="flex items-center gap-1 ml-auto">
            <Clock className="w-3 h-3" />
            {new Date(latestDeployment.created_at).toLocaleDateString()}
          </span>
        )}
      </div>

      {url && deployStatus === "running" && (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-3 flex items-center gap-1 text-xs text-emerald-500 hover:text-emerald-400 transition-colors font-mono truncate"
          onClick={(e) => e.stopPropagation()}
        >
          <ExternalLink className="w-3 h-3 shrink-0" />
          {url.replace("https://", "")}
        </a>
      )}
    </div>
  );
}

export default function TenantDetailPage() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const params = useParams();
  const slug = params.slug as string;
  const { error: toastError, success: toastSuccess } = useToast();

  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [apps, setApps] = useState<Application[]>([]);
  const [latestDeployments, setLatestDeployments] = useState<Record<string, Deployment>>({});
  const [services, setServices] = useState<ManagedService[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingService, setDeletingService] = useState<string | null>(null);
  const [credentialsModal, setCredentialsModal] = useState<{ service: ManagedService; creds: ServiceCredentials | null; loading: boolean } | null>(null);
  const [showPassword, setShowPassword] = useState<Record<string, boolean>>({});
  const [connectModal, setConnectModal] = useState<ManagedService | null>(null);
  const [modifyModal, setModifyModal] = useState<ManagedService | null>(null);
  const [modifyLoading, setModifyLoading] = useState(false);
  const [connectingApp, setConnectingApp] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
  const [deletingTenant, setDeletingTenant] = useState(false);

  const accessToken = (session as typeof session & { accessToken?: string })?.accessToken;

  useEffect(() => {
    if (status === "unauthenticated") router.push("/auth/signin");
  }, [status, router]);

  const load = useCallback(async () => {
    if (status !== "authenticated") return;
    try {
      const [t, a, s] = await Promise.all([
        api.tenants.get(slug, accessToken),
        api.apps.list(slug, accessToken),
        api.services.list(slug, accessToken),
      ]);
      setTenant(t);
      setApps(a);
      setServices(s);

      const depResults = await Promise.allSettled(
        a.map((app) => api.deployments.list(slug, app.slug, accessToken))
      );
      const depMap: Record<string, Deployment> = {};
      depResults.forEach((result, i) => {
        if (result.status === "fulfilled" && result.value.length > 0) {
          depMap[a[i].slug] = result.value[0];
        }
      });
      setLatestDeployments(depMap);
    } catch {
      router.push("/tenants");
    } finally {
      setLoading(false);
    }
  }, [slug, status, accessToken, router]);

  useEffect(() => {
    load();
  }, [load]);

  // Poll services while any is in "provisioning" state
  useEffect(() => {
    const hasProvisioning = services.some((s) => s.status === "provisioning");
    if (!hasProvisioning || status !== "authenticated") return;

    const interval = setInterval(async () => {
      try {
        const updated = await api.services.list(slug, accessToken);
        setServices(updated);
      } catch {
        /* ignore */
      }
    }, 5000);

    return () => clearInterval(interval);
  }, [services, slug, status, accessToken]);

  async function deleteService(serviceName: string) {
    if (!confirm(`Delete service "${serviceName}"?`)) return;
    setDeletingService(serviceName);
    try {
      await api.services.delete(slug, serviceName, accessToken);
      setServices((s) => s.filter((svc) => svc.name !== serviceName));
      toastSuccess(`Service "${serviceName}" deleted`);
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Failed to delete service");
    } finally {
      setDeletingService(null);
    }
  }

  async function openCredentials(svc: ManagedService) {
    setCredentialsModal({ service: svc, creds: null, loading: true });
    setShowPassword({});
    try {
      const creds = await api.services.credentials(slug, svc.name, accessToken);
      setCredentialsModal({ service: svc, creds, loading: false });
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Failed to load credentials");
      setCredentialsModal(null);
    }
  }

  async function connectServiceToApp(appSlug: string) {
    if (!connectModal) return;
    setConnectingApp(true);
    try {
      await api.services.connectToApp(slug, appSlug, connectModal.name, accessToken);
      toastSuccess(`${connectModal.name} connected to ${appSlug}`);
      setConnectModal(null);
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Failed to connect service");
    } finally {
      setConnectingApp(false);
    }
  }

  async function deleteTenant() {
    setDeletingTenant(true);
    try {
      await api.tenants.delete(slug, accessToken);
      router.push("/tenants");
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Failed to delete tenant");
      setDeletingTenant(false);
    }
  }

  if (status === "loading" || loading) {
    return (
      <AppShell userEmail={session?.user?.email}>
        <div className="flex items-center justify-center h-full min-h-[400px]">
          <Loader2 className="w-5 h-5 animate-spin text-gray-400 dark:text-zinc-600" />
        </div>
      </AppShell>
    );
  }

  if (!tenant) return null;

  const runningApps = apps.filter((a) => latestDeployments[a.slug]?.status === "running").length;
  const failedApps = apps.filter((a) => latestDeployments[a.slug]?.status === "failed").length;

  return (
    <AppShell userEmail={session?.user?.email}>
      <div className="p-6 max-w-5xl">
        <Breadcrumb
          items={[
            { label: "Projects", href: "/tenants" },
            { label: tenant.name },
          ]}
        />

        {/* Header */}
        <div className="flex items-start justify-between mb-6">
          <div>
            <div className="flex items-center gap-2.5 mb-1">
              <div className="w-8 h-8 rounded-lg bg-violet-500/10 border border-violet-500/20 flex items-center justify-center">
                <FolderKanban className="w-4 h-4 text-violet-400" />
              </div>
              <h1 className="text-2xl font-bold text-gray-900 dark:text-zinc-100">{tenant.name}</h1>
              <Badge variant={tenant.active ? "success" : "secondary"}>
                {tenant.active ? "active" : "inactive"}
              </Badge>
            </div>
            <p className="text-sm text-gray-400 dark:text-zinc-600 font-mono pl-10">{tenant.namespace}</p>
          </div>
          <button
            onClick={() => setShowDeleteDialog(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-red-900/50 text-red-400 hover:bg-red-950/30 hover:border-red-800 text-xs font-medium transition-colors"
          >
            <Trash2 className="w-3 h-3" />
            Delete Project
          </button>
        </div>

        {/* Delete dialog */}
        {showDeleteDialog && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
            <div className="bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-800 rounded-xl p-6 w-full max-w-md mx-4 shadow-2xl">
              <h2 className="text-base font-semibold text-gray-900 dark:text-zinc-100 mb-2">Delete Project</h2>
              <p className="text-sm text-gray-500 dark:text-zinc-500 mb-1">
                This will permanently delete{" "}
                <strong className="text-gray-800 dark:text-zinc-200">{tenant.name}</strong> and all its
                applications and services. This action cannot be undone.
              </p>
              <p className="text-sm text-gray-500 dark:text-zinc-500 mb-4">
                Type{" "}
                <span className="font-mono font-medium text-gray-800 dark:text-zinc-200">{tenant.slug}</span>{" "}
                to confirm.
              </p>
              <input
                type="text"
                value={deleteConfirmText}
                onChange={(e) => setDeleteConfirmText(e.target.value)}
                placeholder={tenant.slug}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-zinc-700 bg-gray-100 dark:bg-zinc-800 text-sm text-gray-900 dark:text-zinc-100 placeholder:text-gray-400 dark:placeholder:text-zinc-600 focus:outline-none focus:border-red-700 focus:ring-1 focus:ring-red-700/30 font-mono mb-4"
                autoFocus
              />
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => {
                    setShowDeleteDialog(false);
                    setDeleteConfirmText("");
                  }}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium text-gray-500 dark:text-zinc-500 hover:text-gray-900 dark:hover:text-zinc-200 hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={deleteTenant}
                  disabled={deleteConfirmText !== tenant.slug || deletingTenant}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-700 text-white text-xs font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {deletingTenant ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    <Trash2 className="w-3 h-3" />
                  )}
                  Delete Project
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Stats bar */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-6">
          {[
            { label: "Namespace", value: tenant.slug, mono: true },
            { label: "CPU Limit", value: tenant.cpu_limit, mono: true },
            { label: "Memory", value: tenant.memory_limit, mono: true },
            { label: "Storage", value: tenant.storage_limit, mono: true },
          ].map(({ label, value, mono }) => (
            <div
              key={label}
              className="bg-white dark:bg-zinc-900/50 border border-gray-200 dark:border-zinc-800 rounded-xl px-3 py-3 shadow-sm"
            >
              <p className="text-xs text-gray-400 dark:text-zinc-600 mb-1">{label}</p>
              <p className={`text-sm font-medium text-gray-800 dark:text-zinc-200 ${mono ? "font-mono" : ""}`}>
                {value}
              </p>
            </div>
          ))}
          <div className="bg-white dark:bg-zinc-900/50 border border-gray-200 dark:border-zinc-800 rounded-xl px-3 py-3 shadow-sm">
            <p className="text-xs text-gray-400 dark:text-zinc-600 mb-1">App Health</p>
            <div className="flex items-center gap-2">
              {runningApps > 0 && (
                <span className="flex items-center gap-1 text-xs text-emerald-500 font-medium">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                  {runningApps} up
                </span>
              )}
              {failedApps > 0 && (
                <span className="flex items-center gap-1 text-xs text-red-500 font-medium">
                  <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
                  {failedApps} down
                </span>
              )}
              {apps.length === 0 && (
                <span className="text-xs text-gray-400 dark:text-zinc-600">—</span>
              )}
            </div>
          </div>
        </div>

        {/* Tabs */}
        <Tabs defaultValue="apps">
          <TabsList>
            <TabsTrigger value="apps">
              Applications
              <span className="ml-1.5 text-xs text-gray-400 dark:text-zinc-600">{apps.length}</span>
            </TabsTrigger>
            <TabsTrigger value="services">
              Services
              <span className="ml-1.5 text-xs text-gray-400 dark:text-zinc-600">{services.length}</span>
            </TabsTrigger>
            <TabsTrigger value="members">
              <Users className="w-3.5 h-3.5 mr-1" />
              Members
            </TabsTrigger>
            <TabsTrigger value="usage">
              <BarChart3 className="w-3.5 h-3.5 mr-1" />
              Usage
            </TabsTrigger>
            <TabsTrigger value="audit">
              <FileText className="w-3.5 h-3.5 mr-1" />
              Audit Log
            </TabsTrigger>
            <TabsTrigger value="gdpr">
              <Shield className="w-3.5 h-3.5 mr-1" />
              Privacy
            </TabsTrigger>
          </TabsList>

          {/* Applications tab */}
          <TabsContent value="apps" className="pt-5">
            <div className="flex items-center justify-between mb-4">
              <p className="text-sm text-gray-500 dark:text-zinc-500">Deployed applications</p>
              <Link
                href={`/tenants/${slug}/apps/new`}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium transition-colors"
              >
                <Plus className="w-3 h-3" />
                New App
              </Link>
            </div>

            {apps.length === 0 ? (
              <div className="text-center py-16 border border-dashed border-gray-200 dark:border-zinc-800 rounded-xl">
                <Box className="w-8 h-8 mx-auto mb-2 text-gray-400 dark:text-zinc-700" />
                <p className="text-sm text-gray-500 dark:text-zinc-500">No applications yet.</p>
                <Link
                  href={`/tenants/${slug}/apps/new`}
                  className="inline-block mt-2 text-xs text-emerald-500 hover:text-emerald-400 transition-colors"
                >
                  Deploy your first app →
                </Link>
              </div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {apps.map((app) => (
                  <AppCard
                    key={app.id}
                    app={app}
                    tenantSlug={slug}
                    latestDeployment={latestDeployments[app.slug]}
                  />
                ))}
              </div>
            )}
          </TabsContent>

          {/* Services tab */}
          <TabsContent value="services" className="pt-5">
            <div className="flex items-center justify-between mb-4">
              <p className="text-sm text-gray-500 dark:text-zinc-500">
                Managed services (PostgreSQL, Redis, RabbitMQ)
              </p>
              <AddServiceModal
                tenantSlug={slug}
                accessToken={accessToken}
                onCreated={() => load()}
              />
            </div>

            {services.length === 0 ? (
              <div className="text-center py-16 border border-dashed border-gray-200 dark:border-zinc-800 rounded-xl">
                <Database className="w-8 h-8 mx-auto mb-2 text-gray-400 dark:text-zinc-700" />
                <p className="text-sm text-gray-500 dark:text-zinc-500">No managed services yet.</p>
                <p className="text-xs text-gray-400 dark:text-zinc-600 mt-1">Add a PostgreSQL, Redis, or RabbitMQ instance to get started.</p>
              </div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {services.map((svc) => (
                  <div
                    key={svc.id}
                    className="bg-white dark:bg-zinc-900/50 border border-gray-200 dark:border-zinc-800 rounded-xl p-4 hover:border-gray-300 dark:hover:border-zinc-700 transition-colors shadow-sm"
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-2">
                        <ServiceIcon type={svc.service_type} size={24} />
                        <div>
                          <p className="text-sm font-medium text-gray-800 dark:text-zinc-200">{svc.name}</p>
                          <p className="text-xs text-gray-400 dark:text-zinc-600">
                            {svc.service_type} · {svc.tier}
                          </p>
                        </div>
                      </div>
                      <Badge variant={SERVICE_STATUS_VARIANT[svc.status] ?? "secondary"}>
                        {svc.status}
                      </Badge>
                    </div>

                    {svc.connection_hint && (
                      <div className="mt-3 flex items-center gap-1 bg-gray-100 dark:bg-zinc-800 rounded-lg px-2 py-1.5">
                        <p className="text-xs font-mono text-gray-500 dark:text-zinc-500 truncate flex-1">
                          {svc.connection_hint}
                        </p>
                        <CopyButton text={svc.connection_hint} />
                      </div>
                    )}

                    {/* Action buttons */}
                    <div className="mt-3 flex items-center gap-2 border-t border-gray-200 dark:border-zinc-800/50 pt-3">
                      {svc.status === "ready" && (
                        <>
                          <button
                            onClick={() => openCredentials(svc)}
                            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-gray-100 dark:bg-zinc-800 hover:bg-gray-200 dark:hover:bg-zinc-700 text-xs font-medium text-gray-700 dark:text-zinc-300 hover:text-gray-900 dark:hover:text-zinc-100 transition-colors"
                          >
                            <Key className="w-3 h-3" />
                            Credentials
                          </button>
                          <button
                            onClick={() => setConnectModal(svc)}
                            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-gray-100 dark:bg-zinc-800 hover:bg-gray-200 dark:hover:bg-zinc-700 text-xs font-medium text-gray-700 dark:text-zinc-300 hover:text-gray-900 dark:hover:text-zinc-100 transition-colors"
                          >
                            <Link2 className="w-3 h-3" />
                            Connect
                          </button>
                          <button
                            onClick={() => setModifyModal(svc)}
                            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-gray-100 dark:bg-zinc-800 hover:bg-gray-200 dark:hover:bg-zinc-700 text-xs font-medium text-gray-700 dark:text-zinc-300 hover:text-gray-900 dark:hover:text-zinc-100 transition-colors"
                          >
                            <Settings className="w-3 h-3" />
                            Modify
                          </button>
                        </>
                      )}
                      <button
                        onClick={() => deleteService(svc.name)}
                        disabled={deletingService === svc.name}
                        className="ml-auto flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium text-gray-400 dark:text-zinc-600 hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors disabled:opacity-50"
                      >
                        {deletingService === svc.name ? (
                          <Loader2 className="w-3 h-3 animate-spin" />
                        ) : (
                          <Trash2 className="w-3 h-3" />
                        )}
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Credentials Modal */}
            {credentialsModal && (
              <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
                <div className="bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-800 rounded-xl w-full max-w-lg mx-4 shadow-2xl overflow-hidden">
                  <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-zinc-800">
                    <div className="flex items-center gap-2">
                      <Key className="w-4 h-4 text-amber-500" />
                      <h2 className="text-sm font-semibold text-gray-900 dark:text-zinc-100">
                        {credentialsModal.service.name} Credentials
                      </h2>
                    </div>
                    <button
                      onClick={() => setCredentialsModal(null)}
                      className="text-gray-400 dark:text-zinc-600 hover:text-gray-700 dark:hover:text-zinc-300 transition-colors"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>

                  <div className="p-5">
                    {credentialsModal.loading ? (
                      <div className="flex items-center justify-center py-8">
                        <Loader2 className="w-5 h-5 animate-spin text-gray-400 dark:text-zinc-600" />
                        <span className="ml-2 text-sm text-gray-500 dark:text-zinc-500">Reading K8s secret...</span>
                      </div>
                    ) : credentialsModal.creds ? (
                      <div className="space-y-3">
                        {/* Connection string */}
                        {credentialsModal.creds.connection_hint && (
                          <div className="mb-4">
                            <p className="text-xs font-medium text-gray-500 dark:text-zinc-500 mb-1.5 uppercase tracking-wider">Connection String</p>
                            <div className="flex items-center gap-2 bg-gray-100 dark:bg-zinc-800 rounded-lg px-3 py-2.5">
                              <p className="text-xs font-mono text-emerald-400 truncate flex-1">
                                {credentialsModal.creds.connection_hint}
                              </p>
                              <CopyButton text={credentialsModal.creds.connection_hint} />
                            </div>
                          </div>
                        )}

                        {/* Individual credentials */}
                        <p className="text-xs font-medium text-gray-500 dark:text-zinc-500 uppercase tracking-wider">Secret Values</p>
                        <div className="space-y-2">
                          {Object.entries(credentialsModal.creds.credentials).map(([key, value]) => {
                            const isSensitive = /pass|secret|token|key/i.test(key);
                            const isVisible = showPassword[key] || !isSensitive;
                            return (
                              <div
                                key={key}
                                className="flex items-center gap-3 bg-gray-50 dark:bg-zinc-800/70 rounded-lg px-3 py-2.5 group"
                              >
                                <span className="text-xs text-gray-500 dark:text-zinc-500 font-mono w-24 shrink-0 truncate">
                                  {key}
                                </span>
                                <span className="text-xs font-mono text-gray-800 dark:text-zinc-200 flex-1 truncate">
                                  {isVisible ? value : "••••••••••••"}
                                </span>
                                <div className="flex items-center gap-1 shrink-0">
                                  {isSensitive && (
                                    <button
                                      onClick={() => setShowPassword((p) => ({ ...p, [key]: !p[key] }))}
                                      className="text-gray-400 dark:text-zinc-600 hover:text-gray-700 dark:hover:text-zinc-300 transition-colors"
                                    >
                                      {isVisible ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                                    </button>
                                  )}
                                  <CopyButton text={value} />
                                </div>
                              </div>
                            );
                          })}
                        </div>

                        <p className="text-xs text-gray-400 dark:text-zinc-600 mt-4 flex items-center gap-1">
                          <Key className="w-3 h-3" />
                          K8s Secret: <span className="font-mono">{credentialsModal.creds.secret_name}</span>
                        </p>
                      </div>
                    ) : null}
                  </div>
                </div>
              </div>
            )}

            {/* Connect to App Modal */}
            {connectModal && (
              <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
                <div className="bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-800 rounded-xl w-full max-w-md mx-4 shadow-2xl overflow-hidden">
                  <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-zinc-800">
                    <div className="flex items-center gap-2">
                      <Link2 className="w-4 h-4 text-blue-500" />
                      <h2 className="text-sm font-semibold text-gray-900 dark:text-zinc-100">
                        Connect {connectModal.name} to App
                      </h2>
                    </div>
                    <button
                      onClick={() => setConnectModal(null)}
                      className="text-gray-400 dark:text-zinc-600 hover:text-gray-700 dark:hover:text-zinc-300 transition-colors"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>

                  <div className="p-5">
                    <p className="text-xs text-gray-500 dark:text-zinc-500 mb-4">
                      Select an app to inject <span className="font-mono text-gray-700 dark:text-zinc-300">{connectModal.name}</span> credentials as environment variables.
                    </p>

                    {apps.length === 0 ? (
                      <p className="text-sm text-gray-400 dark:text-zinc-600 text-center py-6">No applications to connect.</p>
                    ) : (
                      <div className="space-y-2 max-h-64 overflow-y-auto">
                        {apps.map((app) => (
                          <button
                            key={app.id}
                            onClick={() => connectServiceToApp(app.slug)}
                            disabled={connectingApp}
                            className="w-full flex items-center justify-between px-3 py-2.5 rounded-lg bg-gray-50 dark:bg-zinc-800/50 hover:bg-gray-100 dark:hover:bg-zinc-800 border border-gray-200 dark:border-zinc-800 hover:border-gray-300 dark:hover:border-zinc-700 transition-colors disabled:opacity-50 group"
                          >
                            <div className="flex items-center gap-2">
                              <Server className="w-4 h-4 text-gray-400 dark:text-zinc-600 group-hover:text-gray-500 dark:group-hover:text-zinc-400" />
                              <div className="text-left">
                                <p className="text-sm font-medium text-gray-800 dark:text-zinc-200">{app.name}</p>
                                <p className="text-xs text-gray-400 dark:text-zinc-600 font-mono">{app.slug}</p>
                              </div>
                            </div>
                            {connectingApp ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin text-gray-400 dark:text-zinc-600" />
                            ) : (
                              <Link2 className="w-3.5 h-3.5 text-gray-400 dark:text-zinc-700 group-hover:text-blue-500 transition-colors" />
                            )}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </TabsContent>

          {/* Members tab */}
          <TabsContent value="members" className="pt-5">
            <MembersTab tenantSlug={slug} accessToken={accessToken} />
          </TabsContent>

          {/* Usage tab */}
          <TabsContent value="usage" className="pt-5">
            <BillingTab tenantSlug={slug} accessToken={accessToken} />
          </TabsContent>

          {/* Audit Log tab */}
          <TabsContent value="audit" className="pt-5">
            <AuditLogsTab tenantSlug={slug} accessToken={accessToken} />
          </TabsContent>

          {/* GDPR/Privacy tab */}
          <TabsContent value="gdpr" className="pt-5">
            <GdprTab tenantSlug={slug} accessToken={accessToken} />
          </TabsContent>
        </Tabs>
      </div>

      {/* Modify Service Modal */}
      {modifyModal && (
        <ModifyServiceModal
          open={!!modifyModal}
          onClose={() => setModifyModal(null)}
          onConfirm={async (updates) => {
            setModifyLoading(true);
            try {
              await api.services.update(slug, modifyModal.name, updates, accessToken);
              toastSuccess(`${modifyModal.name} update started`);
              setModifyModal(null);
              load();
            } catch (err) {
              toastError(err instanceof Error ? err.message : "Update failed");
            } finally {
              setModifyLoading(false);
            }
          }}
          loading={modifyLoading}
          service={modifyModal}
        />
      )}
    </AppShell>
  );
}
