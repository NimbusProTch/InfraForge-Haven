"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { useRouter, useParams } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { AddServiceModal } from "@/components/AddServiceModal";
import { api, type Tenant, type Application, type ManagedService } from "@/lib/api";
import {
  ArrowLeft,
  Plus,
  Box,
  Database,
  Loader2,
  GitBranch,
  Server,
  Copy,
  Check,
  Trash2,
} from "lucide-react";

const SERVICE_ICONS: Record<string, string> = {
  postgres: "🐘",
  redis: "🔴",
  rabbitmq: "🐰",
};

const SERVICE_STATUS_VARIANT: Record<string, "success" | "warning" | "destructive" | "secondary"> =
  {
    ready: "success",
    provisioning: "warning",
    failed: "destructive",
    deleting: "secondary",
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
      className="text-gray-400 dark:text-[#555] hover:text-gray-700 dark:hover:text-white transition-colors"
    >
      {copied ? <Check className="w-3 h-3 text-green-500" /> : <Copy className="w-3 h-3" />}
    </button>
  );
}

export default function TenantDetailPage() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const params = useParams();
  const slug = params.slug as string;

  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [apps, setApps] = useState<Application[]>([]);
  const [services, setServices] = useState<ManagedService[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingService, setDeletingService] = useState<string | null>(null);
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
    } catch {
      router.push("/tenants");
    } finally {
      setLoading(false);
    }
  }, [slug, status, accessToken, router]);

  useEffect(() => {
    load();
  }, [load]);

  async function deleteService(serviceName: string) {
    if (!confirm(`Delete service "${serviceName}"?`)) return;
    setDeletingService(serviceName);
    try {
      await api.services.delete(slug, serviceName, accessToken);
      setServices((s) => s.filter((svc) => svc.name !== serviceName));
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to delete service");
    } finally {
      setDeletingService(null);
    }
  }

  async function deleteTenant() {
    setDeletingTenant(true);
    try {
      await api.tenants.delete(slug, accessToken);
      router.push("/tenants");
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to delete tenant");
      setDeletingTenant(false);
    }
  }

  if (status === "loading" || loading) {
    return (
      <AppShell userEmail={session?.user?.email}>
        <div className="flex items-center justify-center h-full min-h-[400px]">
          <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
        </div>
      </AppShell>
    );
  }

  if (!tenant) return null;

  return (
    <AppShell userEmail={session?.user?.email}>
      <div className="p-6 max-w-5xl">
        {/* Header */}
        <div className="flex items-start justify-between mb-6">
          <div className="flex items-center gap-3">
            <Link
              href="/tenants"
              className="text-gray-400 dark:text-[#555] hover:text-gray-900 dark:hover:text-white transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
                  {tenant.name}
                </h1>
                <Badge variant={tenant.active ? "success" : "secondary"}>
                  {tenant.active ? "active" : "inactive"}
                </Badge>
              </div>
              <p className="text-sm text-gray-400 dark:text-[#555] font-mono mt-0.5">
                {tenant.namespace}
              </p>
            </div>
          </div>
          <button
            onClick={() => setShowDeleteDialog(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-red-300 dark:border-red-900/50 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 text-xs font-medium transition-colors"
          >
            <Trash2 className="w-3 h-3" />
            Delete Tenant
          </button>
        </div>

        {/* Delete confirmation dialog */}
        {showDeleteDialog && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
            <div className="bg-white dark:bg-[#1a1a1a] border border-gray-200 dark:border-[#333] rounded-lg p-6 w-full max-w-md mx-4 shadow-xl">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                Delete Tenant
              </h2>
              <p className="text-sm text-gray-500 dark:text-[#888] mb-1">
                This will permanently delete <strong className="text-gray-900 dark:text-white">{tenant.name}</strong> and
                all its applications and services. This action cannot be undone.
              </p>
              <p className="text-sm text-gray-500 dark:text-[#888] mb-4">
                Type <span className="font-mono font-medium text-gray-900 dark:text-white">{tenant.slug}</span> to confirm.
              </p>
              <input
                type="text"
                value={deleteConfirmText}
                onChange={(e) => setDeleteConfirmText(e.target.value)}
                placeholder={tenant.slug}
                className="w-full px-3 py-2 rounded-md border border-gray-200 dark:border-[#333] bg-white dark:bg-[#141414] text-sm text-gray-900 dark:text-white placeholder:text-gray-300 dark:placeholder:text-[#444] focus:outline-none focus:ring-2 focus:ring-red-500/30 font-mono mb-4"
                autoFocus
              />
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => {
                    setShowDeleteDialog(false);
                    setDeleteConfirmText("");
                  }}
                  className="px-3 py-1.5 rounded-md text-xs font-medium text-gray-600 dark:text-[#888] hover:bg-gray-100 dark:hover:bg-[#222] transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={deleteTenant}
                  disabled={deleteConfirmText !== tenant.slug || deletingTenant}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-red-600 hover:bg-red-700 text-white text-xs font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {deletingTenant ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    <Trash2 className="w-3 h-3" />
                  )}
                  Delete Tenant
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Info bar */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          {[
            { label: "Slug", value: tenant.slug },
            { label: "CPU", value: tenant.cpu_limit },
            { label: "Memory", value: tenant.memory_limit },
            { label: "Storage", value: tenant.storage_limit },
          ].map(({ label, value }) => (
            <div
              key={label}
              className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg px-3 py-2.5"
            >
              <p className="text-xs text-gray-400 dark:text-[#555]">{label}</p>
              <p className="text-sm font-medium text-gray-900 dark:text-white font-mono mt-0.5">
                {value}
              </p>
            </div>
          ))}
        </div>

        {/* Tabs */}
        <Tabs defaultValue="apps">
          <TabsList>
            <TabsTrigger value="apps">
              Applications
              <span className="ml-1.5 text-xs text-gray-400 dark:text-[#555]">
                {apps.length}
              </span>
            </TabsTrigger>
            <TabsTrigger value="services">
              Services
              <span className="ml-1.5 text-xs text-gray-400 dark:text-[#555]">
                {services.length}
              </span>
            </TabsTrigger>
          </TabsList>

          {/* Applications tab */}
          <TabsContent value="apps" className="pt-5">
            <div className="flex items-center justify-between mb-4">
              <p className="text-sm text-gray-500 dark:text-[#888]">
                Deployed applications
              </p>
              <Link
                href={`/tenants/${slug}/apps/new`}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium transition-colors"
              >
                <Plus className="w-3 h-3" />
                New App
              </Link>
            </div>

            {apps.length === 0 ? (
              <div className="text-center py-16 text-gray-400 dark:text-[#555]">
                <Box className="w-8 h-8 mx-auto mb-2 opacity-40" />
                <p className="text-sm">No applications yet.</p>
                <Link
                  href={`/tenants/${slug}/apps/new`}
                  className="inline-block mt-2 text-xs text-blue-600 hover:text-blue-500"
                >
                  Deploy your first app →
                </Link>
              </div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {apps.map((app) => (
                  <Link
                    key={app.id}
                    href={`/tenants/${slug}/apps/${app.slug}`}
                    className="block bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg p-4 hover:bg-gray-50 dark:hover:bg-[#1a1a1a] transition-colors group"
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-2.5">
                        <div className="w-8 h-8 rounded-md bg-gray-100 dark:bg-[#1f1f1f] flex items-center justify-center shrink-0">
                          <Server className="w-4 h-4 text-gray-500 dark:text-[#666]" />
                        </div>
                        <div>
                          <p className="text-sm font-medium text-gray-900 dark:text-white">
                            {app.name}
                          </p>
                          <p className="text-xs text-gray-400 dark:text-[#555] font-mono mt-0.5 truncate max-w-[200px]">
                            {app.slug}
                          </p>
                        </div>
                      </div>
                    </div>
                    <div className="mt-3 flex items-center gap-3 text-xs text-gray-400 dark:text-[#555]">
                      <span className="flex items-center gap-1">
                        <GitBranch className="w-3 h-3" />
                        {app.branch}
                      </span>
                      <span>{app.replicas} replica{app.replicas !== 1 ? "s" : ""}</span>
                    </div>
                    <p className="mt-2 text-xs text-gray-400 dark:text-[#555] font-mono truncate">
                      {app.repo_url}
                    </p>
                  </Link>
                ))}
              </div>
            )}
          </TabsContent>

          {/* Services tab */}
          <TabsContent value="services" className="pt-5">
            <div className="flex items-center justify-between mb-4">
              <p className="text-sm text-gray-500 dark:text-[#888]">
                Managed services (PostgreSQL, Redis, RabbitMQ)
              </p>
              <AddServiceModal
                tenantSlug={slug}
                accessToken={accessToken}
                onCreated={() => load()}
              />
            </div>

            {services.length === 0 ? (
              <div className="text-center py-16 text-gray-400 dark:text-[#555]">
                <Database className="w-8 h-8 mx-auto mb-2 opacity-40" />
                <p className="text-sm">No managed services yet.</p>
              </div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {services.map((svc) => (
                  <div
                    key={svc.id}
                    className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg p-4"
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-lg">{SERVICE_ICONS[svc.service_type]}</span>
                        <div>
                          <p className="text-sm font-medium text-gray-900 dark:text-white">
                            {svc.name}
                          </p>
                          <p className="text-xs text-gray-400 dark:text-[#555]">
                            {svc.service_type} · {svc.tier}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant={SERVICE_STATUS_VARIANT[svc.status] ?? "secondary"}>
                          {svc.status}
                        </Badge>
                        <button
                          onClick={() => deleteService(svc.name)}
                          disabled={deletingService === svc.name}
                          className="text-gray-400 dark:text-[#444] hover:text-red-500 transition-colors disabled:opacity-50"
                        >
                          {deletingService === svc.name ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <Trash2 className="w-3.5 h-3.5" />
                          )}
                        </button>
                      </div>
                    </div>

                    {svc.connection_hint && (
                      <div className="mt-3 flex items-center gap-1">
                        <p className="text-xs font-mono text-gray-400 dark:text-[#555] truncate flex-1">
                          {svc.connection_hint}
                        </p>
                        <CopyButton text={svc.connection_hint} />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </TabsContent>
        </Tabs>
      </div>
    </AppShell>
  );
}
