"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useSession } from "next-auth/react";
import { useRouter, useParams } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/ui/badge";
import { Breadcrumb } from "@/components/Breadcrumb";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { useToast } from "@/components/Toast";
import { api, type Application, type Deployment, getLogsUrl } from "@/lib/api";
import AppSettings from "@/components/AppSettings";
import ObservabilityTab from "@/components/ObservabilityTab";
import {
  Activity,
  GitBranch,
  Hammer,
  Rocket,
  RotateCcw,
  Loader2,
  Package,
  Terminal,
  StopCircle,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Settings,
  Check,
  X,
  Circle,
  ExternalLink,
} from "lucide-react";

const LB_IP = process.env.NEXT_PUBLIC_LB_IP ?? "";

// ---- Pipeline types and helpers ----

type PipelineStepStatus = "pending" | "running" | "success" | "failed";

interface PipelineStep {
  key: string;
  label: string;
  status: PipelineStepStatus;
}

// Derive pipeline step statuses from a deployment object
function derivePipelineSteps(deployment: Deployment): PipelineStep[] {
  const keys = [
    { key: "clone", label: "Clone" },
    { key: "detect", label: "Detect" },
    { key: "build", label: "Build" },
    { key: "push", label: "Push" },
    { key: "deploy", label: "Deploy" },
  ];

  let statuses: PipelineStepStatus[];

  switch (deployment.status) {
    case "pending":
      statuses = ["pending", "pending", "pending", "pending", "pending"];
      break;
    case "building":
      statuses = ["success", "success", "running", "pending", "pending"];
      break;
    case "deploying":
      statuses = ["success", "success", "success", "success", "running"];
      break;
    case "running":
      statuses = ["success", "success", "success", "success", "success"];
      break;
    case "failed":
      // If image_tag exists, build+push succeeded so deploy step failed
      if (deployment.image_tag) {
        statuses = ["success", "success", "success", "success", "failed"];
      } else {
        statuses = ["success", "success", "failed", "pending", "pending"];
      }
      break;
    default:
      statuses = ["pending", "pending", "pending", "pending", "pending"];
  }

  return keys.map((step, i) => ({ ...step, status: statuses[i] }));
}

// ---- Pipeline step status icon ----

function StepStatusIcon({ status }: { status: PipelineStepStatus }) {
  switch (status) {
    case "success":
      return (
        <div className="w-5 h-5 rounded-full bg-emerald-500/15 flex items-center justify-center">
          <Check className="w-3 h-3 text-emerald-400" />
        </div>
      );
    case "running":
      return (
        <div className="w-5 h-5 rounded-full bg-blue-500/15 flex items-center justify-center">
          <Loader2 className="w-3 h-3 text-blue-400 animate-spin" />
        </div>
      );
    case "failed":
      return (
        <div className="w-5 h-5 rounded-full bg-red-500/15 flex items-center justify-center">
          <X className="w-3 h-3 text-red-400" />
        </div>
      );
    default:
      return (
        <div className="w-5 h-5 rounded-full bg-[#222] flex items-center justify-center">
          <Circle className="w-2.5 h-2.5 text-[#555]" />
        </div>
      );
  }
}

// ---- Pipeline visualization component ----

function PipelineVisualization({
  steps,
  compact = false,
}: {
  steps: PipelineStep[];
  compact?: boolean;
}) {
  const connectorColor = (prev: PipelineStepStatus, curr: PipelineStepStatus) => {
    if (prev === "success" && curr !== "pending") return "bg-emerald-500/40";
    if (prev === "success") return "bg-emerald-500/20";
    return "bg-[#222]";
  };

  const textColor = (s: PipelineStepStatus) => {
    if (s === "running") return "text-blue-400";
    if (s === "success") return "text-emerald-400";
    if (s === "failed") return "text-red-400";
    return "text-[#555]";
  };

  return (
    <div className={`flex items-center ${compact ? "gap-1" : "gap-0"} w-full`}>
      {steps.map((step, i) => (
        <div key={step.key} className="flex items-center flex-1 last:flex-none">
          <div className="flex flex-col items-center gap-1">
            {compact ? (
              <StepStatusIcon status={step.status} />
            ) : (
              <div
                className={`
                  flex items-center gap-2 px-3 py-2 rounded-lg border transition-colors
                  ${step.status === "running" ? "border-blue-500/30 bg-blue-500/5" : ""}
                  ${step.status === "success" ? "border-emerald-500/20 bg-emerald-500/5" : ""}
                  ${step.status === "failed" ? "border-red-500/30 bg-red-500/5" : ""}
                  ${step.status === "pending" ? "border-[#222] bg-[#141414]" : ""}
                `}
              >
                <StepStatusIcon status={step.status} />
                <span className={`text-xs font-medium ${textColor(step.status)}`}>
                  {step.label}
                </span>
              </div>
            )}
            {compact && (
              <span className={`text-[10px] font-medium ${step.status === "pending" ? "text-[#444]" : textColor(step.status)}`}>
                {step.label}
              </span>
            )}
          </div>
          {/* Connector line between steps */}
          {i < steps.length - 1 && (
            <div
              className={`flex-1 h-px mx-1 ${compact ? "min-w-2" : "min-w-4"} ${connectorColor(
                step.status,
                steps[i + 1].status
              )}`}
            />
          )}
        </div>
      ))}
    </div>
  );
}

// ---- Status variant and color maps ----

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

const STATUS_DOT_COLORS: Record<string, string> = {
  running: "bg-emerald-500",
  building: "bg-yellow-500 animate-pulse",
  deploying: "bg-blue-500 animate-pulse",
  pending: "bg-gray-500",
  failed: "bg-red-500",
};

// ---- Deployment card component ----

function DeploymentCard({
  deployment,
  onRollback,
  rolling,
}: {
  deployment: Deployment;
  onRollback: (id: string) => void;
  rolling: string | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const isActive = ["building", "deploying"].includes(deployment.status);
  const isFailed = deployment.status === "failed";
  const pipelineSteps = derivePipelineSteps(deployment);

  return (
    <div
      className={`border-b border-[#1e1e1e] last:border-0 transition-colors ${
        isActive ? "bg-[#0d1117]" : ""
      }`}
    >
      {/* Main row */}
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          {/* Status dot */}
          <div className="shrink-0">
            <div
              className={`w-2 h-2 rounded-full ${
                STATUS_DOT_COLORS[deployment.status] ?? "bg-gray-500"
              }`}
            />
          </div>

          {/* Commit info */}
          <div className="min-w-0 shrink-0">
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono text-[#ccc]">
                {deployment.commit_sha ? deployment.commit_sha.slice(0, 7) : "manual"}
              </span>
              <Badge variant={DEPLOY_STATUS_VARIANT[deployment.status] ?? "secondary"}>
                {deployment.status}
              </Badge>
            </div>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-xs text-[#555]">
                {new Date(deployment.created_at).toLocaleString()}
              </span>
              {deployment.image_tag && deployment.status === "running" && (
                <span className="text-xs font-mono text-[#444]">
                  {deployment.image_tag.split(":").pop()}
                </span>
              )}
            </div>
          </div>

          {/* Compact pipeline for active/failed/running deployments on wider screens */}
          {(isActive || isFailed || deployment.status === "running") && (
            <div className="hidden md:flex flex-1 mx-4">
              <PipelineVisualization steps={pipelineSteps} compact />
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 shrink-0 ml-3">
          {/* Expand/collapse for failed deployments with error messages */}
          {isFailed && deployment.error_message && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="text-[#444] hover:text-white transition-colors"
              title="Show error details"
            >
              {expanded ? (
                <ChevronUp className="w-3.5 h-3.5" />
              ) : (
                <ChevronDown className="w-3.5 h-3.5" />
              )}
            </button>
          )}
          {/* Rollback button */}
          {["running", "failed"].includes(deployment.status) && deployment.image_tag && (
            <button
              onClick={() => onRollback(deployment.id)}
              disabled={rolling === deployment.id}
              title="Rollback to this deployment"
              className="text-[#444] hover:text-white transition-colors disabled:opacity-50"
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

      {/* Expanded error message */}
      {expanded && isFailed && deployment.error_message && (
        <div className="px-4 pb-3">
          <div className="bg-red-500/5 border border-red-500/20 rounded-md p-3">
            <pre className="text-xs font-mono text-red-400 whitespace-pre-wrap break-all">
              {deployment.error_message}
            </pre>
          </div>
        </div>
      )}

      {/* Pipeline visualization for active/failed builds on mobile */}
      {(isActive || isFailed) && (
        <div className="md:hidden px-4 pb-3">
          <PipelineVisualization steps={pipelineSteps} compact />
        </div>
      )}
    </div>
  );
}

// ---- Build log terminal (shown inline during active builds) ----

function BuildLogTerminal({
  logs,
  streaming,
  onStop,
}: {
  logs: string;
  streaming: boolean;
  onStop: () => void;
}) {
  const endRef = useRef<HTMLDivElement>(null);

  // Auto-scroll as new logs arrive
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  if (!logs && !streaming) return null;

  return (
    <div className="mt-4">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Terminal className="w-3.5 h-3.5 text-[#555]" />
          <span className="text-xs font-medium text-[#888]">Build Output</span>
          {streaming && (
            <span className="flex items-center gap-1.5 text-xs text-emerald-500">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              streaming
            </span>
          )}
        </div>
        {streaming && (
          <button
            onClick={onStop}
            className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs text-[#666] hover:text-white transition-colors"
          >
            <StopCircle className="w-3 h-3" />
            Stop
          </button>
        )}
      </div>
      <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg overflow-hidden">
        <pre className="p-4 text-xs font-mono text-emerald-400/80 overflow-auto max-h-[400px] whitespace-pre-wrap break-all leading-relaxed">
          {logs}
          <div ref={endRef} />
        </pre>
      </div>
    </div>
  );
}

// ---- Main page component ----

export default function AppDetailPage() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const params = useParams();
  const tenantSlug = params.slug as string;
  const appSlug = params.appSlug as string;
  const { error: toastError, success: toastSuccess } = useToast();

  const [app, setApp] = useState<Application | null>(null);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<"build" | "deploy" | null>(null);
  const [rolling, setRolling] = useState<string | null>(null);

  // Edit state (kept for header display sync with AppSettings)
  const [editName, setEditName] = useState("");
  const [editRepoUrl, setEditRepoUrl] = useState("");
  const [editBranch, setEditBranch] = useState("");
  const [editReplicas, setEditReplicas] = useState(1);

  // Logs state
  const [logs, setLogs] = useState<string>("");
  const [streaming, setStreaming] = useState(false);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Polling ref for deployment status
  const deployPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Track previous active state for auto-stream start/stop
  const prevActiveRef = useRef(false);

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

  // Initial data load
  useEffect(() => {
    if (status !== "authenticated") return;
    async function load() {
      try {
        const [a, d] = await Promise.all([
          api.apps.get(tenantSlug, appSlug, accessToken),
          api.deployments.list(tenantSlug, appSlug, accessToken).catch(() => []),
        ]);
        setApp(a);
        setEditName(a.name);
        setEditRepoUrl(a.repo_url);
        setEditBranch(a.branch);
        setEditReplicas(a.replicas);
        setDeployments(d as Deployment[]);
      } catch {
        router.push(`/tenants/${tenantSlug}`);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [tenantSlug, appSlug, status, accessToken, router]);

  // Determine if there is an active build/deploy
  const latestDeployment = deployments[0];
  const isActiveBuild =
    latestDeployment != null &&
    ["building", "deploying", "pending"].includes(latestDeployment.status);

  // Poll deployments every 5s while there is an active build
  useEffect(() => {
    if (isActiveBuild) {
      deployPollRef.current = setInterval(() => {
        loadDeployments();
      }, 5000);
    }
    return () => {
      if (deployPollRef.current) {
        clearInterval(deployPollRef.current);
        deployPollRef.current = null;
      }
    };
  }, [isActiveBuild, loadDeployments]);

  // Auto-start log streaming when a build becomes active, stop when it finishes
  useEffect(() => {
    const shouldStream =
      latestDeployment != null &&
      ["building", "deploying"].includes(latestDeployment.status);

    if (shouldStream && !prevActiveRef.current && !streaming) {
      startLogs();
    }

    if (!shouldStream && prevActiveRef.current && streaming) {
      stopLogs();
    }

    prevActiveRef.current = !!shouldStream;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latestDeployment?.status]);

  // Auto-scroll the Logs tab terminal
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  async function startLogs() {
    // Abort any previous stream
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    setLogs("");
    setStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;
    const url = getLogsUrl(tenantSlug, appSlug, accessToken);

    try {
      const res = await fetch(url, {
        headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
        signal: controller.signal,
      });
      if (!res.ok || !res.body) {
        setLogs(`[error: ${res.status} ${res.statusText}]\n`);
        setStreaming(false);
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // Parse SSE lines from buffer
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          for (const line of part.split("\n")) {
            if (line.startsWith("data: ")) {
              const text = line.slice(6);
              // Stop on end marker
              if (text === "[end]" || text === "[end of logs]") continue;
              setLogs((prev) => prev + text + "\n");
            }
          }
        }
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        // User cancelled - expected
      } else {
        setLogs((prev) => prev + `[connection error]\n`);
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }

  function stopLogs() {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
  }

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      if (deployPollRef.current) clearInterval(deployPollRef.current);
    };
  }, []);

  async function handleBuild() {
    setActionLoading("build");
    try {
      await api.deployments.build(tenantSlug, appSlug, accessToken);
      await loadDeployments();
      toastSuccess("Build started");
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Build failed");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleDeploy() {
    setActionLoading("deploy");
    try {
      await api.deployments.deploy(tenantSlug, appSlug, accessToken);
      await loadDeployments();
      toastSuccess("Deploy started");
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Deploy failed");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleRollback(deploymentId: string) {
    setRolling(deploymentId);
    try {
      await api.deployments.rollback(tenantSlug, appSlug, deploymentId, accessToken);
      await loadDeployments();
      toastSuccess("Rollback initiated");
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Rollback failed");
    } finally {
      setRolling(null);
    }
  }

  // Save and delete are now handled by the AppSettings component

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

  const currentStatus = latestDeployment?.status;
  const appPublicUrl = LB_IP
    ? `https://${appSlug}.${tenantSlug}.apps.${LB_IP}.sslip.io`
    : null;

  return (
    <AppShell userEmail={session?.user?.email}>
      <div className="p-6 max-w-5xl">
        <Breadcrumb
          items={[
            { label: "Tenants", href: "/tenants" },
            { label: tenantSlug, href: `/tenants/${tenantSlug}` },
            { label: app.name },
          ]}
        />

        {/* Header */}
        <div className="flex items-start justify-between mb-6">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-semibold text-gray-900 dark:text-white">{app.name}</h1>
              {currentStatus && (
                <Badge variant={DEPLOY_STATUS_VARIANT[currentStatus] ?? "secondary"}>
                  {currentStatus}
                </Badge>
              )}
            </div>
            <div className="flex items-center gap-3 mt-1">
              <p className="text-xs text-gray-400 dark:text-[#555] font-mono">
                <span
                  className="hover:text-blue-500 cursor-pointer"
                  onClick={() => window.open(app.repo_url, "_blank")}
                >
                  {app.repo_url.replace("https://github.com/", "")}
                </span>
                <ChevronRight className="inline w-3 h-3 mx-0.5" />
                <span className="inline-flex items-center gap-0.5">
                  <GitBranch className="w-3 h-3" />
                  {app.branch}
                </span>
              </p>
              {appPublicUrl && currentStatus === "running" && (
                <a
                  href={appPublicUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-blue-500 hover:text-blue-400 transition-colors font-mono"
                >
                  <ExternalLink className="w-3 h-3" />
                  {appPublicUrl.replace("https://", "")}
                </a>
              )}
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

        {/* Active build: pipeline visualization + auto-streaming logs */}
        {isActiveBuild && latestDeployment && (
          <div className="mb-6 bg-[#141414] border border-[#222] rounded-lg p-4">
            <div className="flex items-center gap-2 mb-3">
              <Loader2 className="w-3.5 h-3.5 text-blue-400 animate-spin" />
              <span className="text-xs font-medium text-[#888]">
                Deployment in progress
              </span>
              {latestDeployment.commit_sha && (
                <span className="text-xs font-mono text-[#555]">
                  {latestDeployment.commit_sha.slice(0, 7)}
                </span>
              )}
            </div>
            <PipelineVisualization steps={derivePipelineSteps(latestDeployment)} />
            {/* Build logs auto-stream during active builds */}
            <BuildLogTerminal logs={logs} streaming={streaming} onStop={stopLogs} />
          </div>
        )}

        {/* App info bar */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          {[
            { label: "Replicas", value: String(app.replicas) },
            { label: "Branch", value: app.branch },
            { label: "Image", value: app.image_tag ? app.image_tag.split(":").pop() ?? "--" : "--" },
            {
              label: "Webhook",
              value: app.webhook_token ? `...${app.webhook_token.slice(-8)}` : "--",
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
            <TabsTrigger value="observability">
              <Activity className="w-3.5 h-3.5 mr-1" />
              Observability
            </TabsTrigger>
            <TabsTrigger value="logs">
              <Terminal className="w-3.5 h-3.5 mr-1" />
              Logs
            </TabsTrigger>
            <TabsTrigger value="settings">
              <Settings className="w-3.5 h-3.5 mr-1" />
              Settings
            </TabsTrigger>
          </TabsList>

          {/* Deployments tab */}
          <TabsContent value="deployments" className="pt-5">
            {deployments.length === 0 ? (
              <div className="text-center py-16 text-gray-400 dark:text-[#555]">
                <Package className="w-8 h-8 mx-auto mb-2 opacity-40" />
                <p className="text-sm">No deployments yet.</p>
                <p className="text-xs mt-1">Click &quot;Build&quot; to trigger the first build.</p>
              </div>
            ) : (
              <div className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg overflow-hidden">
                {deployments.map((d) => (
                  <DeploymentCard
                    key={d.id}
                    deployment={d}
                    onRollback={handleRollback}
                    rolling={rolling}
                  />
                ))}
              </div>
            )}
          </TabsContent>

          {/* Observability tab */}
          <TabsContent value="observability" className="pt-5">
            <ObservabilityTab
              tenantSlug={tenantSlug}
              appSlug={appSlug}
              appName={app.name}
              deployments={deployments}
              logs={logs}
              streaming={streaming}
              onStartLogs={startLogs}
              onStopLogs={stopLogs}
            />
          </TabsContent>

          {/* Logs tab */}
          <TabsContent value="logs" className="pt-5">
            <div className="flex items-center gap-2 mb-3">
              {!streaming ? (
                <button
                  onClick={startLogs}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium transition-colors"
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
                <span className="flex items-center gap-1.5 text-xs text-emerald-500">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
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

            <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg overflow-hidden">
              <pre className="p-4 text-xs font-mono text-emerald-400/80 overflow-auto min-h-[240px] max-h-[500px] whitespace-pre-wrap break-all leading-relaxed">
                {logs ||
                  "# Click 'Stream logs' to start receiving live logs from running pods...\n"}
                <div ref={logsEndRef} />
              </pre>
            </div>
          </TabsContent>

          {/* Settings tab - delegated to AppSettings component */}
          <TabsContent value="settings" className="pt-5">
            <AppSettings
              tenantSlug={tenantSlug}
              app={app}
              accessToken={accessToken}
              onSaved={(updated) => {
                setApp(updated);
                setEditName(updated.name);
                setEditRepoUrl(updated.repo_url);
                setEditBranch(updated.branch);
                setEditReplicas(updated.replicas);
              }}
            />
          </TabsContent>
        </Tabs>
      </div>
    </AppShell>
  );
}
