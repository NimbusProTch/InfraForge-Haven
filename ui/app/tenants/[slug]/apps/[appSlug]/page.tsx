"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useSession } from "next-auth/react";
import { useRouter, useParams } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { api, type Application, type Deployment, getLogsUrl } from "@/lib/api";
import {
  ArrowLeft,
  GitBranch,
  GitCommit,
  Hammer,
  Rocket,
  RotateCcw,
  Loader2,
  Package,
  Terminal,
  StopCircle,
  ChevronRight,
} from "lucide-react";

const DEPLOY_STATUS_VARIANT: Record<
  string,
  "success" | "warning" | "destructive" | "secondary" | "default"
> = {
  running: "success",
  building: "warning",
  deploying: "warning",
  pending: "secondary",
  failed: "destructive",
};

function DeploymentRow({
  deployment,
  onRollback,
  rolling,
}: {
  deployment: Deployment;
  onRollback: (id: string) => void;
  rolling: string | null;
}) {
  return (
    <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 dark:border-[#1e1e1e] last:border-0">
      <div className="flex items-center gap-3 min-w-0">
        <div className="w-8 h-8 rounded-md bg-gray-100 dark:bg-[#1f1f1f] flex items-center justify-center shrink-0">
          <GitCommit className="w-3.5 h-3.5 text-gray-500 dark:text-[#666]" />
        </div>
        <div className="min-w-0">
          <p className="text-xs font-mono text-gray-700 dark:text-[#ccc] truncate">
            {deployment.commit_sha?.slice(0, 12) || "—"}
          </p>
          {deployment.image_tag && (
            <p className="text-xs font-mono text-gray-400 dark:text-[#555] truncate mt-0.5">
              {deployment.image_tag.split(":").pop()}
            </p>
          )}
          {deployment.error_message && (
            <p className="text-xs text-red-400 truncate mt-0.5">{deployment.error_message}</p>
          )}
        </div>
      </div>
      <div className="flex items-center gap-3 shrink-0 ml-3">
        <span className="text-xs text-gray-400 dark:text-[#555] hidden sm:block">
          {new Date(deployment.created_at).toLocaleString()}
        </span>
        <Badge variant={DEPLOY_STATUS_VARIANT[deployment.status] ?? "secondary"}>
          {deployment.status}
        </Badge>
        {["running", "failed"].includes(deployment.status) && deployment.image_tag && (
          <button
            onClick={() => onRollback(deployment.id)}
            disabled={rolling === deployment.id}
            title="Rollback to this deployment"
            className="text-gray-400 dark:text-[#444] hover:text-gray-700 dark:hover:text-white transition-colors disabled:opacity-50"
          >
            {rolling === deployment.id ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <RotateCcw className="w-3.5 h-3.5" />
            )}
          </button>
        )}
      </div>
    </div>
  );
}

export default function AppDetailPage() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const params = useParams();
  const tenantSlug = params.slug as string;
  const appSlug = params.appSlug as string;

  const [app, setApp] = useState<Application | null>(null);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<"build" | "deploy" | null>(null);
  const [rolling, setRolling] = useState<string | null>(null);

  // Logs state
  const [logs, setLogs] = useState<string>("");
  const [streaming, setStreaming] = useState(false);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);

  const accessToken = (session as typeof session & { accessToken?: string })?.accessToken;

  useEffect(() => {
    if (status === "unauthenticated") router.push("/auth/signin");
  }, [status, router]);

  const loadDeployments = useCallback(async () => {
    if (status !== "authenticated") return;
    try {
      const list = await api.deployments.list(tenantSlug, appSlug, accessToken);
      setDeployments(list);
    } catch {
      /* ignore */
    }
  }, [tenantSlug, appSlug, status, accessToken]);

  useEffect(() => {
    if (status !== "authenticated") return;
    async function load() {
      try {
        const [a, d] = await Promise.all([
          api.apps.get(tenantSlug, appSlug, accessToken),
          api.deployments.list(tenantSlug, appSlug, accessToken).catch(() => []),
        ]);
        setApp(a);
        setDeployments(d as Deployment[]);
      } catch {
        router.push(`/tenants/${tenantSlug}`);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [tenantSlug, appSlug, status, accessToken, router]);

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  function startLogs() {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    setLogs("");
    setStreaming(true);
    const url = getLogsUrl(tenantSlug, appSlug);
    const es = new EventSource(url);
    esRef.current = es;

    es.onmessage = (e) => {
      setLogs((prev) => prev + e.data + "\n");
    };

    es.onerror = () => {
      setStreaming(false);
      es.close();
      esRef.current = null;
    };
  }

  function stopLogs() {
    esRef.current?.close();
    esRef.current = null;
    setStreaming(false);
  }

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      esRef.current?.close();
    };
  }, []);

  async function handleBuild() {
    setActionLoading("build");
    try {
      await api.deployments.build(tenantSlug, appSlug, accessToken);
      await loadDeployments();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Build failed");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleDeploy() {
    setActionLoading("deploy");
    try {
      await api.deployments.deploy(tenantSlug, appSlug, accessToken);
      await loadDeployments();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Deploy failed");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleRollback(deploymentId: string) {
    setRolling(deploymentId);
    try {
      await api.deployments.rollback(tenantSlug, appSlug, deploymentId, accessToken);
      await loadDeployments();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Rollback failed");
    } finally {
      setRolling(null);
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

  if (!app) return null;

  const latestDeployment = deployments[0];
  const currentStatus = latestDeployment?.status;

  return (
    <AppShell userEmail={session?.user?.email}>
      <div className="p-6 max-w-5xl">
        {/* Header */}
        <div className="flex items-start justify-between mb-6">
          <div className="flex items-center gap-3">
            <Link
              href={`/tenants/${tenantSlug}`}
              className="text-gray-400 dark:text-[#555] hover:text-gray-900 dark:hover:text-white transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-semibold text-gray-900 dark:text-white">{app.name}</h1>
                {currentStatus && (
                  <Badge variant={DEPLOY_STATUS_VARIANT[currentStatus] ?? "secondary"}>
                    {currentStatus}
                  </Badge>
                )}
              </div>
              <p className="text-xs text-gray-400 dark:text-[#555] font-mono mt-0.5">
                <span
                  className="hover:text-blue-500 cursor-pointer"
                  onClick={() => {
                    const parts = app.repo_url
                      .replace(/\.git$/, "")
                      .split("/");
                    const [owner, repo] = parts.slice(-2);
                    if (owner && repo) window.open(app.repo_url, "_blank");
                  }}
                >
                  {app.repo_url}
                </span>
                <ChevronRight className="inline w-3 h-3 mx-0.5" />
                <span className="inline-flex items-center gap-0.5">
                  <GitBranch className="w-3 h-3" />
                  {app.branch}
                </span>
              </p>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={handleBuild}
              disabled={!!actionLoading}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#141414] hover:bg-gray-50 dark:hover:bg-[#1a1a1a] text-gray-700 dark:text-[#ccc] text-xs font-medium transition-colors disabled:opacity-50"
            >
              {actionLoading === "build" ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Hammer className="w-3.5 h-3.5" />
              )}
              Build
            </button>
            <button
              onClick={handleDeploy}
              disabled={!!actionLoading || !app.image_tag}
              title={!app.image_tag ? "No image built yet" : "Deploy current image"}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-medium transition-colors"
            >
              {actionLoading === "deploy" ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Rocket className="w-3.5 h-3.5" />
              )}
              Deploy
            </button>
          </div>
        </div>

        {/* App info bar */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          {[
            { label: "Replicas", value: String(app.replicas) },
            { label: "Branch", value: app.branch },
            { label: "Image", value: app.image_tag ? app.image_tag.split(":").pop() ?? "—" : "—" },
            {
              label: "Webhook",
              value: app.webhook_token ? `…${app.webhook_token.slice(-8)}` : "—",
            },
          ].map(({ label, value }) => (
            <div
              key={label}
              className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg px-3 py-2.5"
            >
              <p className="text-xs text-gray-400 dark:text-[#555]">{label}</p>
              <p className="text-sm font-medium text-gray-900 dark:text-white font-mono mt-0.5 truncate">
                {value}
              </p>
            </div>
          ))}
        </div>

        {/* Tabs */}
        <Tabs defaultValue="deployments">
          <TabsList>
            <TabsTrigger value="deployments">
              Deployments
              <span className="ml-1.5 text-xs text-gray-400 dark:text-[#555]">
                {deployments.length}
              </span>
            </TabsTrigger>
            <TabsTrigger value="logs">
              <Terminal className="w-3.5 h-3.5 mr-1" />
              Logs
            </TabsTrigger>
          </TabsList>

          {/* Deployments tab */}
          <TabsContent value="deployments" className="pt-5">
            {deployments.length === 0 ? (
              <div className="text-center py-16 text-gray-400 dark:text-[#555]">
                <Package className="w-8 h-8 mx-auto mb-2 opacity-40" />
                <p className="text-sm">No deployments yet.</p>
                <p className="text-xs mt-1">Click "Build" to trigger the first build.</p>
              </div>
            ) : (
              <div className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg overflow-hidden">
                {deployments.map((d) => (
                  <DeploymentRow
                    key={d.id}
                    deployment={d}
                    onRollback={handleRollback}
                    rolling={rolling}
                  />
                ))}
              </div>
            )}
          </TabsContent>

          {/* Logs tab */}
          <TabsContent value="logs" className="pt-5">
            <div className="flex items-center gap-2 mb-3">
              {!streaming ? (
                <button
                  onClick={startLogs}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-green-600 hover:bg-green-700 text-white text-xs font-medium transition-colors"
                >
                  <Terminal className="w-3.5 h-3.5" />
                  Stream logs
                </button>
              ) : (
                <button
                  onClick={stopLogs}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-red-600 hover:bg-red-700 text-white text-xs font-medium transition-colors"
                >
                  <StopCircle className="w-3.5 h-3.5" />
                  Stop
                </button>
              )}
              {streaming && (
                <span className="flex items-center gap-1.5 text-xs text-green-500">
                  <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                  live
                </span>
              )}
              {logs && !streaming && (
                <button
                  onClick={() => setLogs("")}
                  className="text-xs text-gray-400 dark:text-[#555] hover:text-gray-700 dark:hover:text-[#888] transition-colors"
                >
                  Clear
                </button>
              )}
            </div>

            <div className="bg-gray-950 dark:bg-[#050505] border border-gray-800 dark:border-[#1a1a1a] rounded-lg overflow-hidden">
              <pre className="p-4 text-xs font-mono text-green-400 overflow-auto min-h-[240px] max-h-[500px] whitespace-pre-wrap break-all">
                {logs ||
                  "# Click 'Stream logs' to start receiving live logs from running pods...\n"}
                <div ref={logsEndRef} />
              </pre>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </AppShell>
  );
}
