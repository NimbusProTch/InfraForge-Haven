"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useSession } from "next-auth/react";
import { useRouter, useParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/ui/badge";
import { Breadcrumb } from "@/components/Breadcrumb";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { useToast } from "@/components/Toast";
import { api, type Application, type Deployment, type BuildStatus, type ContainerStatus, getLogsUrl } from "@/lib/api";
import AppSettings from "@/components/AppSettings";
import ObservabilityTab from "@/components/ObservabilityTab";
import EnvironmentsTab from "@/components/EnvironmentsTab";
import DomainsTab from "@/components/DomainsTab";
import CronJobsTab from "@/components/CronJobsTab";
import VolumesTab from "@/components/VolumesTab";
import CanaryTab from "@/components/CanaryTab";
import { AnsiTerminal } from "@/components/ui/ansi-terminal";
import { BuildModal, DeployModal } from "@/components/BuildDeployModal";
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
  Layers,
  Globe,
  Timer,
  HardDrive,
  GitCompare,
  Check,
  X,
  Circle,
  ExternalLink,
  RefreshCw,
} from "lucide-react";

const LB_IP = process.env.NEXT_PUBLIC_LB_IP ?? "";

// ---- Pipeline types ----

type PipelineStepStatus = "pending" | "running" | "success" | "failed";

interface PipelineStep {
  key: string;
  label: string;
  status: PipelineStepStatus;
  duration?: string | null;
}

// Map container name to pipeline step key
const CONTAINER_TO_STEP: Record<string, string> = {
  "git-clone": "clone",
  "nixpacks": "detect",
  "buildctl": "build",
  "build": "build",
};

function containerStatusToPipeline(cs: ContainerStatus): PipelineStepStatus {
  if (cs.status === "completed") return "success";
  if (cs.status === "running") return "running";
  if (cs.status === "failed") return "failed";
  return "pending";
}

function derivePipelineSteps(deployment: Deployment, buildStatus?: BuildStatus | null): PipelineStep[] {
  const keys = [
    { key: "clone", label: "Clone" },
    { key: "detect", label: "Detect" },
    { key: "build", label: "Build" },
    { key: "push", label: "Push" },
    { key: "deploy", label: "Deploy" },
  ];

  // Use real container status if available
  if (buildStatus?.containers && buildStatus.containers.length > 0) {
    const containerMap: Record<string, ContainerStatus> = {};
    for (const c of buildStatus.containers) {
      const stepKey = CONTAINER_TO_STEP[c.name] ?? c.name;
      containerMap[stepKey] = c;
    }

    return keys.map((step) => {
      const cs = containerMap[step.key];
      if (cs) {
        return { ...step, status: containerStatusToPipeline(cs), duration: cs.duration };
      }
      // Push = build completed, Deploy = deployment status
      if (step.key === "push") {
        const buildCs = containerMap["build"];
        if (buildCs?.status === "completed") {
          return { ...step, status: "success" as PipelineStepStatus, duration: null };
        }
        return { ...step, status: "pending" as PipelineStepStatus, duration: null };
      }
      if (step.key === "deploy") {
        if (deployment.status === "deploying") return { ...step, status: "running" as PipelineStepStatus, duration: null };
        if (deployment.status === "running") return { ...step, status: "success" as PipelineStepStatus, duration: null };
        if (deployment.status === "failed" && deployment.image_tag) return { ...step, status: "failed" as PipelineStepStatus, duration: null };
        return { ...step, status: "pending" as PipelineStepStatus, duration: null };
      }
      return { ...step, status: "pending" as PipelineStepStatus, duration: null };
    });
  }

  // Fallback: derive from deployment status
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
      if (deployment.image_tag) {
        statuses = ["success", "success", "success", "success", "failed"];
      } else {
        statuses = ["success", "success", "failed", "pending", "pending"];
      }
      break;
    default:
      statuses = ["pending", "pending", "pending", "pending", "pending"];
  }

  return keys.map((step, i) => ({ ...step, status: statuses[i], duration: null }));
}

// ---- Enterprise Pipeline Visualization ----

const STEP_STYLES: Record<PipelineStepStatus, { border: string; bg: string; icon: string; text: string }> = {
  success: {
    border: "border-l-emerald-500 border-emerald-200 dark:border-emerald-500/20",
    bg: "bg-emerald-50 dark:bg-emerald-500/5",
    icon: "bg-emerald-500/15 border-emerald-500/30 text-emerald-500",
    text: "text-emerald-700 dark:text-emerald-400",
  },
  running: {
    border: "border-l-blue-500 border-blue-200 dark:border-blue-500/20",
    bg: "bg-blue-50 dark:bg-blue-500/5",
    icon: "bg-blue-500/15 border-blue-500/30 text-blue-500",
    text: "text-blue-700 dark:text-blue-400",
  },
  failed: {
    border: "border-l-red-500 border-red-200 dark:border-red-500/20",
    bg: "bg-red-50 dark:bg-red-500/5",
    icon: "bg-red-500/15 border-red-500/30 text-red-500",
    text: "text-red-700 dark:text-red-400",
  },
  pending: {
    border: "border-l-gray-300 dark:border-l-zinc-700 border-gray-200 dark:border-zinc-800 border-dashed",
    bg: "bg-gray-50 dark:bg-zinc-900/30",
    icon: "bg-gray-100 dark:bg-zinc-800 border-gray-300 dark:border-zinc-700 text-gray-400 dark:text-zinc-600",
    text: "text-gray-400 dark:text-zinc-600",
  },
};

function StepStatusIcon({ status, size = "md" }: { status: PipelineStepStatus; size?: "sm" | "md" }) {
  const s = size === "sm" ? "w-5 h-5" : "w-7 h-7";
  const iconSize = size === "sm" ? "w-2.5 h-2.5" : "w-3.5 h-3.5";
  const style = STEP_STYLES[status];

  const icon = status === "success" ? <Check className={iconSize} /> :
    status === "running" ? <Loader2 className={`${iconSize} animate-spin`} /> :
    status === "failed" ? <X className={iconSize} /> :
    <Circle className={size === "sm" ? "w-2 h-2" : "w-2.5 h-2.5"} />;

  return (
    <div className={`${s} rounded-full border flex items-center justify-center ${style.icon}`}>
      {icon}
    </div>
  );
}

function PipelineVisualization({
  steps,
  compact = false,
  activeStep,
  onStepClick,
}: {
  steps: PipelineStep[];
  compact?: boolean;
  activeStep?: string | null;
  onStepClick?: (stepKey: string) => void;
}) {
  const isClickable = !!onStepClick;

  if (compact) {
    return (
      <div className="flex items-center gap-1 w-full">
        {steps.map((step, i) => (
          <div key={step.key} className="flex items-center flex-1 last:flex-none">
            <div className="flex flex-col items-center gap-1">
              <StepStatusIcon status={step.status} size="sm" />
              <span className={`text-[10px] font-medium ${STEP_STYLES[step.status].text}`}>
                {step.label}
              </span>
            </div>
            {i < steps.length - 1 && (
              <div className={`flex-1 h-px mx-1 min-w-2 ${
                step.status === "success" ? "bg-emerald-300 dark:bg-emerald-500/30" :
                step.status === "failed" ? "bg-red-300 dark:bg-red-500/20" :
                "bg-gray-200 dark:bg-zinc-800"
              }`} />
            )}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="flex items-stretch gap-0 w-full">
      {steps.map((step, i) => {
        const style = STEP_STYLES[step.status];
        const isActive = activeStep === step.key;
        return (
          <div key={step.key} className="flex items-center flex-1 last:flex-none">
            <div
              className={`
                flex items-center gap-2.5 px-4 py-3 rounded-xl border-l-4 border shadow-sm transition-all w-full
                ${style.border} ${style.bg}
                ${isActive ? "ring-2 ring-blue-400/50 shadow-md scale-[1.02]" : ""}
                ${isClickable && step.status !== "pending" ? "cursor-pointer hover:shadow-md hover:scale-[1.02]" : ""}
              `}
              onClick={() => isClickable && step.status !== "pending" && onStepClick?.(step.key)}
            >
              <StepStatusIcon status={step.status} />
              <div className="flex flex-col min-w-0">
                <span className={`text-xs font-semibold ${style.text}`}>
                  {step.label}
                </span>
                {step.duration && (
                  <span className="text-[10px] text-gray-400 dark:text-zinc-500 font-mono">{step.duration}</span>
                )}
              </div>
            </div>
            {i < steps.length - 1 && (
              <div className="flex items-center px-1 shrink-0">
                <ChevronRight className={`w-4 h-4 ${
                  step.status === "success" ? "text-emerald-400" :
                  step.status === "failed" ? "text-red-400" :
                  "text-gray-300 dark:text-zinc-700"
                }`} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

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
  building: "bg-amber-500 animate-pulse",
  deploying: "bg-blue-500 animate-pulse",
  pending: "bg-zinc-500",
  failed: "bg-red-500",
};

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
      className={`border-b border-gray-100 dark:border-zinc-800/60 last:border-0 transition-colors ${
        isActive ? "bg-blue-500/3" : ""
      }`}
    >
      <div className="flex items-center justify-between px-4 py-3.5">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <div className="shrink-0">
            <div
              className={`w-2 h-2 rounded-full ${
                STATUS_DOT_COLORS[deployment.status] ?? "bg-zinc-500"
              }`}
            />
          </div>

          <div className="min-w-0 shrink-0">
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono text-gray-700 dark:text-zinc-300">
                {deployment.commit_sha ? deployment.commit_sha.slice(0, 7) : "manual"}
              </span>
              <Badge variant={DEPLOY_STATUS_VARIANT[deployment.status] ?? "secondary"}>
                {deployment.status}
              </Badge>
            </div>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-xs text-gray-400 dark:text-zinc-600">
                {new Date(deployment.created_at).toLocaleString()}
              </span>
              {deployment.image_tag && deployment.status === "running" && (
                <span className="text-xs font-mono text-gray-400 dark:text-zinc-700">
                  {deployment.image_tag.split(":").pop()}
                </span>
              )}
            </div>
          </div>

          {(isActive || isFailed || deployment.status === "running") && (
            <div className="hidden md:flex flex-1 mx-4">
              <PipelineVisualization steps={pipelineSteps} compact />
            </div>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0 ml-3">
          {isFailed && deployment.error_message && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="text-gray-400 dark:text-zinc-600 hover:text-gray-700 dark:hover:text-zinc-300 transition-colors"
              title="Show error details"
            >
              {expanded ? (
                <ChevronUp className="w-3.5 h-3.5" />
              ) : (
                <ChevronDown className="w-3.5 h-3.5" />
              )}
            </button>
          )}
          {["running", "failed"].includes(deployment.status) && deployment.image_tag && (
            <button
              onClick={() => onRollback(deployment.id)}
              disabled={rolling === deployment.id}
              title="Rollback to this deployment"
              className="text-gray-400 dark:text-zinc-600 hover:text-gray-700 dark:hover:text-zinc-300 transition-colors disabled:opacity-50"
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

      {expanded && isFailed && deployment.error_message && (
        <div className="px-4 pb-3">
          <div className="bg-red-500/5 border border-red-500/20 rounded-lg p-3">
            <pre className="text-xs font-mono text-red-400 whitespace-pre-wrap break-all">
              {deployment.error_message}
            </pre>
          </div>
        </div>
      )}

      {(isActive || isFailed) && (
        <div className="md:hidden px-4 pb-3">
          <PipelineVisualization steps={pipelineSteps} compact />
        </div>
      )}
    </div>
  );
}

// Step key → container name mapping for log filtering
const STEP_TO_CONTAINER: Record<string, string> = {
  clone: "git-clone",
  detect: "nixpacks",
  build: "buildctl",
};

function parseLogSections(logs: string): Map<string, string> {
  const sections = new Map<string, string>();
  const regex = /^--- (git-clone|nixpacks|buildctl) ---$/m;
  const parts = logs.split(regex);

  // parts: [preamble, "git-clone", logs1, "nixpacks", logs2, "buildctl", logs3]
  let currentContainer = "__preamble__";
  for (const part of parts) {
    if (["git-clone", "nixpacks", "buildctl"].includes(part)) {
      currentContainer = part;
    } else {
      const existing = sections.get(currentContainer) ?? "";
      sections.set(currentContainer, existing + part);
    }
  }
  return sections;
}

function BuildLogTerminal({
  logs,
  streaming,
  onStop,
  activeLogStep,
  onStepFilter,
}: {
  logs: string;
  streaming: boolean;
  onStop: () => void;
  activeLogStep?: string | null;
  onStepFilter?: (step: string | null) => void;
}) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  if (!logs && !streaming) return null;

  // Parse logs into sections and filter if a step is active
  const sections = parseLogSections(logs);
  const containerName = activeLogStep ? STEP_TO_CONTAINER[activeLogStep] : null;
  const filteredLogs = containerName && sections.has(containerName)
    ? sections.get(containerName)!.trim()
    : logs;

  const filterTabs = [
    { key: null, label: "All" },
    { key: "clone", label: "Clone" },
    { key: "detect", label: "Detect" },
    { key: "build", label: "Build" },
  ];

  return (
    <div className="mt-4">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Terminal className="w-3.5 h-3.5 text-gray-400 dark:text-zinc-600" />
          <span className="text-xs font-medium text-gray-500 dark:text-zinc-500">Build Output</span>
          {streaming && (
            <span className="flex items-center gap-1.5 text-xs text-emerald-500">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              streaming
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* Log filter tabs */}
          {onStepFilter && sections.size > 1 && (
            <div className="flex items-center gap-0.5 bg-gray-100 dark:bg-zinc-800 rounded-lg p-0.5">
              {filterTabs.map((tab) => (
                <button
                  key={tab.key ?? "all"}
                  onClick={() => onStepFilter(tab.key)}
                  className={`px-2 py-1 rounded text-[10px] font-medium transition-colors ${
                    activeLogStep === tab.key
                      ? "bg-white dark:bg-zinc-700 text-gray-900 dark:text-zinc-100 shadow-sm"
                      : "text-gray-500 dark:text-zinc-500 hover:text-gray-700 dark:hover:text-zinc-300"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          )}
          {streaming && (
            <button
              onClick={onStop}
              className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs text-gray-400 dark:text-zinc-600 hover:text-gray-700 dark:hover:text-zinc-300 transition-colors"
            >
              <StopCircle className="w-3 h-3" />
              Stop
            </button>
          )}
        </div>
      </div>
      <div className="bg-zinc-950 border border-gray-200 dark:border-zinc-800 rounded-xl overflow-hidden">
        <div className="flex items-center gap-1.5 px-4 py-2.5 border-b border-gray-200 dark:border-zinc-800">
          <span className="w-2.5 h-2.5 rounded-full bg-red-500/40" />
          <span className="w-2.5 h-2.5 rounded-full bg-amber-500/40" />
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/40" />
          <span className="text-xs text-zinc-700 ml-2 font-mono">
            {containerName ? `build.log — ${containerName}` : "build.log"}
          </span>
        </div>
        <AnsiTerminal
          content={filteredLogs}
          className="p-4 max-h-[400px]"
          endRef={endRef}
        />
      </div>
    </div>
  );
}

// ---- Main page ----

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
  const [syncing, setSyncing] = useState(false);
  const [syncStatus, setSyncStatus] = useState<{ health: string; sync: string } | null>(null);
  const [argoHistory, setArgoHistory] = useState<Array<Record<string, unknown>>>([]);

  const [editName, setEditName] = useState("");
  const [editRepoUrl, setEditRepoUrl] = useState("");
  const [editBranch, setEditBranch] = useState("");
  const [editReplicas, setEditReplicas] = useState(1);

  const [logs, setLogs] = useState<string>("");
  const [streaming, setStreaming] = useState(false);
  const logsEndRef = useRef<HTMLDivElement>(null);

  const [buildStatus, setBuildStatus] = useState<BuildStatus | null>(null);
  const [activeLogStep, setActiveLogStep] = useState<string | null>(null);
  const [showBuildModal, setShowBuildModal] = useState(false);
  const [showDeployModal, setShowDeployModal] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const deployPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
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

  const loadSyncStatus = useCallback(async () => {
    if (status !== "authenticated") return;
    try {
      const s = await api.deployments.syncStatus(tenantSlug, appSlug, accessToken);
      setSyncStatus(s);
    } catch {
      /* ignore - ArgoCD may not be configured */
    }
  }, [tenantSlug, appSlug, status, accessToken]);

  const loadArgoHistory = useCallback(async () => {
    if (status !== "authenticated") return;
    try {
      const h = await api.deployments.deployHistory(tenantSlug, appSlug, accessToken);
      setArgoHistory(h);
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
        setEditName(a.name);
        setEditRepoUrl(a.repo_url);
        setEditBranch(a.branch);
        setEditReplicas(a.replicas);
        setDeployments(d as Deployment[]);
        void loadSyncStatus();
        void loadArgoHistory();
      } catch {
        router.push(`/tenants/${tenantSlug}`);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [tenantSlug, appSlug, status, accessToken, router, loadSyncStatus, loadArgoHistory]);

  const loadApp = useCallback(async () => {
    if (status !== "authenticated") return;
    try {
      const a = await api.apps.get(tenantSlug, appSlug, accessToken);
      setApp(a);
      setEditName(a.name);
      setEditRepoUrl(a.repo_url);
      setEditBranch(a.branch);
      setEditReplicas(a.replicas);
    } catch { /* ignore */ }
  }, [tenantSlug, appSlug, status, accessToken]);

  const latestDeployment = deployments[0];
  const isActiveBuild =
    latestDeployment != null &&
    ["building", "deploying", "pending"].includes(latestDeployment.status);

  const loadBuildStatus = useCallback(async () => {
    if (status !== "authenticated") return;
    try {
      const bs = await api.deployments.buildStatus(tenantSlug, appSlug, accessToken);
      setBuildStatus(bs);
    } catch {
      /* ignore */
    }
  }, [tenantSlug, appSlug, status, accessToken]);

  useEffect(() => {
    if (isActiveBuild) {
      deployPollRef.current = setInterval(() => {
        loadDeployments();
        loadBuildStatus();
      }, 5000);
      // Initial load
      loadBuildStatus();
    } else {
      setBuildStatus(null);
      setActiveLogStep(null);
    }
    return () => {
      if (deployPollRef.current) {
        clearInterval(deployPollRef.current);
        deployPollRef.current = null;
      }
    };
  }, [isActiveBuild, loadDeployments, loadBuildStatus]);

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

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  async function startLogs() {
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

        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          for (const line of part.split("\n")) {
            if (line.startsWith("data: ")) {
              const text = line.slice(6);
              if (text === "[end]" || text === "[end of logs]") continue;
              setLogs((prev) => prev + text + "\n");
            }
          }
        }
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        // User cancelled
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

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      if (deployPollRef.current) clearInterval(deployPollRef.current);
    };
  }, []);

  async function handleBuildConfirm(opts: { branch?: string; build_env_vars?: Record<string, string> }) {
    setShowBuildModal(false);
    setActionLoading("build");
    try {
      const body = (opts.branch || opts.build_env_vars) ? opts : undefined;
      await api.deployments.build(tenantSlug, appSlug, accessToken, body);
      await loadDeployments();
      toastSuccess("Build started");
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Build failed");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleDeployConfirm(opts: { replicas?: number; resource_cpu_limit?: string; resource_memory_limit?: string }) {
    setShowDeployModal(false);
    setActionLoading("deploy");
    try {
      const body = (opts.replicas || opts.resource_cpu_limit || opts.resource_memory_limit) ? opts : undefined;
      await api.deployments.deploy(tenantSlug, appSlug, accessToken, body);
      await loadDeployments();
      if (opts.replicas) await loadApp();
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

  async function handleSync() {
    setSyncing(true);
    try {
      await api.deployments.sync(tenantSlug, appSlug, accessToken);
      toastSuccess("ArgoCD sync triggered");
      setTimeout(() => void loadSyncStatus(), 2000);
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Sync failed");
    } finally {
      setSyncing(false);
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
            { label: "Projects", href: "/tenants" },
            { label: tenantSlug, href: `/tenants/${tenantSlug}` },
            { label: app.name },
          ]}
        />

        {/* Header */}
        <div className="flex items-start justify-between mb-6">
          <div>
            <div className="flex items-center gap-2.5 mb-1">
              <div className="w-8 h-8 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center shrink-0">
                <span className="text-sm">⚡</span>
              </div>
              <h1 className="text-2xl font-bold text-gray-900 dark:text-zinc-100">{app.name}</h1>
              {currentStatus && (
                <Badge variant={DEPLOY_STATUS_VARIANT[currentStatus] ?? "secondary"}>
                  {currentStatus}
                </Badge>
              )}
            </div>
            <div className="flex items-center gap-3 mt-1 pl-10">
              <p className="text-xs text-gray-400 dark:text-zinc-600 font-mono">
                <span
                  className="hover:text-blue-400 cursor-pointer transition-colors"
                  onClick={() => window.open(app.repo_url, "_blank")}
                >
                  {app.repo_url.replace("https://github.com/", "")}
                </span>
                <ChevronRight className="inline w-3 h-3 mx-0.5 text-gray-400 dark:text-zinc-700" />
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
                  className="inline-flex items-center gap-1 text-xs text-emerald-500 hover:text-emerald-400 transition-colors font-mono"
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
              onClick={() => setShowBuildModal(true)}
              disabled={!!actionLoading}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-gray-200 dark:border-zinc-800 hover:border-gray-300 dark:hover:border-zinc-700 bg-white dark:bg-zinc-900/50 hover:bg-gray-50 dark:hover:bg-zinc-800/50 text-gray-500 dark:text-zinc-400 hover:text-gray-900 dark:hover:text-zinc-200 text-xs font-medium transition-colors disabled:opacity-50"
            >
              {actionLoading === "build" ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Hammer className="w-3.5 h-3.5" />
              )}
              Build
            </button>
            <button
              onClick={() => setShowDeployModal(true)}
              disabled={!!actionLoading || !app.image_tag}
              title={!app.image_tag ? "No image built yet" : "Deploy current image"}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-medium transition-colors"
            >
              {actionLoading === "deploy" ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Rocket className="w-3.5 h-3.5" />
              )}
              Deploy
            </button>
            {/* Scale dropdown */}
            <div className="relative group">
              <button
                className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-gray-200 dark:border-zinc-800 hover:border-gray-300 dark:hover:border-zinc-700 bg-white dark:bg-zinc-900/50 hover:bg-gray-50 dark:hover:bg-zinc-800/50 text-gray-500 dark:text-zinc-400 hover:text-gray-900 dark:hover:text-zinc-200 text-xs font-medium transition-colors"
              >
                <Layers className="w-3.5 h-3.5" />
                Scale
                <ChevronDown className="w-3 h-3" />
              </button>
              <div className="absolute right-0 mt-1 w-36 bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-800 rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-10">
                {[1, 2, 3, 5].map((n) => (
                  <button
                    key={n}
                    onClick={async () => {
                      try {
                        await api.apps.update(tenantSlug, appSlug, { replicas: n }, accessToken);
                        await loadApp();
                        toastSuccess(`Scaled to ${n} replica${n > 1 ? "s" : ""}`);
                      } catch (err) {
                        toastError(err instanceof Error ? err.message : "Scale failed");
                      }
                    }}
                    className={`w-full text-left px-3 py-2 text-xs transition-colors ${
                      app.replicas === n
                        ? "text-emerald-400 bg-emerald-500/10"
                        : "text-gray-500 dark:text-zinc-400 hover:text-gray-900 dark:hover:text-zinc-200 hover:bg-gray-100 dark:hover:bg-zinc-800"
                    }`}
                  >
                    {n} replica{n > 1 ? "s" : ""} {app.replicas === n ? "✓" : ""}
                  </button>
                ))}
              </div>
            </div>
            {/* Restart */}
            <button
              onClick={async () => {
                if (!confirm("This will restart all pods. Continue?")) return;
                try {
                  await api.apps.restart(tenantSlug, appSlug, accessToken);
                  toastSuccess("Restart initiated");
                } catch (err) {
                  toastError(err instanceof Error ? err.message : "Restart failed");
                }
              }}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-gray-200 dark:border-zinc-800 hover:border-gray-300 dark:hover:border-zinc-700 bg-white dark:bg-zinc-900/50 hover:bg-gray-50 dark:hover:bg-zinc-800/50 text-gray-500 dark:text-zinc-400 hover:text-gray-900 dark:hover:text-zinc-200 text-xs font-medium transition-colors"
              title="Restart all pods"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Restart
            </button>
            <button
              onClick={handleSync}
              disabled={syncing}
              title="Force ArgoCD to re-sync this application with the GitOps repository"
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-gray-200 dark:border-zinc-800 hover:border-gray-300 dark:hover:border-zinc-700 bg-white dark:bg-zinc-900/50 hover:bg-gray-50 dark:hover:bg-zinc-800/50 text-gray-500 dark:text-zinc-400 hover:text-gray-900 dark:hover:text-zinc-200 text-xs font-medium transition-colors disabled:opacity-50"
            >
              {syncing ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <RefreshCw className="w-3.5 h-3.5" />
              )}
              ArgoCD Sync
            </button>
          </div>
        </div>

        {/* Active build: pipeline + logs */}
        {isActiveBuild && latestDeployment && (
          <div className="mb-6 bg-white dark:bg-zinc-900/80 border border-gray-200 dark:border-zinc-800 rounded-xl p-4 shadow-sm">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
              <span className="text-xs font-medium text-gray-500 dark:text-zinc-400">
                Deployment in progress
              </span>
              {latestDeployment.commit_sha && (
                <span className="text-xs font-mono text-gray-400 dark:text-zinc-600">
                  {latestDeployment.commit_sha.slice(0, 7)}
                </span>
              )}
            </div>
            <PipelineVisualization
              steps={derivePipelineSteps(latestDeployment, buildStatus)}
              activeStep={activeLogStep}
              onStepClick={(key) => setActiveLogStep(activeLogStep === key ? null : key)}
            />
            {/* Per-container status summary */}
            {buildStatus?.containers && buildStatus.containers.length > 0 && (
              <div className="flex items-center gap-3 mt-3 px-1">
                {buildStatus.containers.map((c) => (
                  <div key={c.name} className="flex items-center gap-1.5">
                    <span className={`w-1.5 h-1.5 rounded-full ${
                      c.status === "completed" ? "bg-emerald-500" :
                      c.status === "running" ? "bg-blue-500 animate-pulse" :
                      c.status === "failed" ? "bg-red-500" : "bg-zinc-600"
                    }`} />
                    <span className="text-[10px] text-gray-500 dark:text-zinc-500 font-mono">{c.name}</span>
                    {c.duration && <span className="text-[10px] text-gray-400 dark:text-zinc-600">{c.duration}</span>}
                    {c.exit_code !== null && c.exit_code !== 0 && (
                      <span className="text-[10px] text-red-400">exit {c.exit_code}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
            <BuildLogTerminal
              logs={logs}
              streaming={streaming}
              onStop={stopLogs}
              activeLogStep={activeLogStep}
              onStepFilter={(step) => setActiveLogStep(step)}
            />
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
              className="bg-white dark:bg-zinc-900/50 border border-gray-200 dark:border-zinc-800 rounded-xl px-3 py-3 shadow-sm"
            >
              <p className="text-xs text-gray-400 dark:text-zinc-600 mb-1">{label}</p>
              <p className="text-sm font-medium text-gray-800 dark:text-zinc-200 font-mono truncate">{value}</p>
            </div>
          ))}
        </div>

        {/* ArgoCD status bar */}
        {syncStatus && (
          <div className="mb-4 flex items-center gap-3 px-3 py-2 rounded-lg border border-gray-200 dark:border-zinc-800 bg-gray-50 dark:bg-zinc-900/30">
            <span className="text-xs text-gray-400 dark:text-zinc-600">ArgoCD</span>
            <div className="flex items-center gap-2">
              <span className={`text-xs font-medium ${syncStatus.health === "Healthy" ? "text-emerald-400" : syncStatus.health === "Degraded" ? "text-red-400" : "text-amber-400"}`}>
                {syncStatus.health}
              </span>
              <span className="text-gray-300 dark:text-zinc-700">·</span>
              <span className={`text-xs font-medium ${syncStatus.sync === "Synced" ? "text-emerald-400" : syncStatus.sync === "OutOfSync" ? "text-amber-400" : "text-gray-500 dark:text-zinc-400"}`}>
                {syncStatus.sync}
              </span>
            </div>
          </div>
        )}

        {/* Tabs */}
        <Tabs defaultValue="deployments">
          <TabsList>
            <TabsTrigger value="deployments">
              Deployments
              <span className="ml-1.5 text-xs text-gray-400 dark:text-zinc-600">{deployments.length}</span>
            </TabsTrigger>
            <TabsTrigger value="observability">
              <Activity className="w-3.5 h-3.5 mr-1" />
              Observability
            </TabsTrigger>
            <TabsTrigger value="logs">
              <Terminal className="w-3.5 h-3.5 mr-1" />
              Logs
            </TabsTrigger>
            <TabsTrigger value="environments">
              <Layers className="w-3.5 h-3.5 mr-1" />
              Environments
            </TabsTrigger>
            <TabsTrigger value="domains">
              <Globe className="w-3.5 h-3.5 mr-1" />
              Domains
            </TabsTrigger>
            <TabsTrigger value="cronjobs">
              <Timer className="w-3.5 h-3.5 mr-1" />
              Jobs
            </TabsTrigger>
            <TabsTrigger value="storage">
              <HardDrive className="w-3.5 h-3.5 mr-1" />
              Storage
            </TabsTrigger>
            <TabsTrigger value="canary">
              <GitCompare className="w-3.5 h-3.5 mr-1" />
              Canary
            </TabsTrigger>
            <TabsTrigger value="settings">
              <Settings className="w-3.5 h-3.5 mr-1" />
              Settings
            </TabsTrigger>
          </TabsList>

          {/* Deployments tab */}
          <TabsContent value="deployments" className="pt-5">
            {deployments.length === 0 ? (
              <div className="text-center py-16 border border-dashed border-gray-200 dark:border-zinc-800 rounded-xl">
                <Package className="w-8 h-8 mx-auto mb-2 text-gray-400 dark:text-zinc-700" />
                <p className="text-sm text-gray-500 dark:text-zinc-500">No deployments yet.</p>
                <p className="text-xs mt-1 text-gray-400 dark:text-zinc-600">Click &quot;Build&quot; to trigger the first build.</p>
              </div>
            ) : (
              <div className="bg-white dark:bg-zinc-900/50 border border-gray-200 dark:border-zinc-800 rounded-xl overflow-hidden shadow-sm">
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
            {argoHistory.length > 0 && (
              <div className="mt-6">
                <h4 className="text-xs font-medium text-gray-500 dark:text-zinc-500 uppercase tracking-wider mb-3">ArgoCD Revisions</h4>
                <div className="bg-white dark:bg-zinc-900/50 border border-gray-200 dark:border-zinc-800 rounded-xl overflow-hidden shadow-sm">
                  {argoHistory.slice(0, 10).map((h, i) => {
                    const revision = h.revision as number | undefined;
                    const deployedAt = h.deployedAt as string | undefined;
                    const message = (h.source as Record<string, unknown> | undefined)?.repoURL as string ?? "";
                    return (
                      <div key={i} className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100 dark:border-zinc-800/60 last:border-0">
                        <div className="flex items-center gap-3">
                          <span className="text-xs font-mono text-gray-500 dark:text-zinc-500">r{revision}</span>
                          <span className="text-xs text-gray-400 dark:text-zinc-600 truncate max-w-xs">{message}</span>
                        </div>
                        <div className="flex items-center gap-3 shrink-0">
                          {deployedAt && (
                            <span className="text-xs text-gray-400 dark:text-zinc-700">{new Date(deployedAt).toLocaleString()}</span>
                          )}
                          {typeof revision === "number" && (
                            <button
                              onClick={async () => {
                                try {
                                  await api.deployments.argoCDRollback(tenantSlug, appSlug, revision, accessToken);
                                  toastSuccess(`Rolled back to revision ${revision}`);
                                } catch (err) {
                                  toastError(err instanceof Error ? err.message : "Rollback failed");
                                }
                              }}
                              className="text-gray-400 dark:text-zinc-600 hover:text-gray-700 dark:hover:text-zinc-300 transition-colors"
                              title={`Rollback to revision ${revision}`}
                            >
                              <RotateCcw className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
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
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium transition-colors"
                >
                  <Terminal className="w-3.5 h-3.5" />
                  Stream logs
                </button>
              ) : (
                <button
                  onClick={stopLogs}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-700 text-white text-xs font-medium transition-colors"
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
                  className="text-xs text-gray-400 dark:text-zinc-600 hover:text-gray-500 dark:hover:text-zinc-400 transition-colors"
                >
                  Clear
                </button>
              )}
            </div>

            <div className="bg-zinc-950 border border-gray-200 dark:border-zinc-800 rounded-xl overflow-hidden">
              <div className="flex items-center gap-1.5 px-4 py-2.5 border-b border-gray-200 dark:border-zinc-800">
                <span className="w-2.5 h-2.5 rounded-full bg-red-500/40" />
                <span className="w-2.5 h-2.5 rounded-full bg-amber-500/40" />
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/40" />
                <span className="text-xs text-zinc-700 ml-2 font-mono">
                  {app.name} · live logs
                </span>
                {streaming && (
                  <span className="ml-auto flex items-center gap-1 text-xs text-emerald-500">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                    live
                  </span>
                )}
              </div>
              <AnsiTerminal
                content={logs || "# Click 'Stream logs' to start receiving live logs from running pods...\n"}
                className="p-4 min-h-[240px] max-h-[500px]"
                endRef={logsEndRef}
              />
            </div>
          </TabsContent>

          {/* Environments tab */}
          <TabsContent value="environments" className="pt-5">
            <EnvironmentsTab
              tenantSlug={tenantSlug}
              appSlug={app.slug}
              accessToken={accessToken}
            />
          </TabsContent>

          {/* Domains tab */}
          <TabsContent value="domains" className="pt-5">
            <DomainsTab
              tenantSlug={tenantSlug}
              appSlug={app.slug}
              accessToken={accessToken}
            />
          </TabsContent>

          {/* CronJobs tab */}
          <TabsContent value="cronjobs" className="pt-5">
            <CronJobsTab
              tenantSlug={tenantSlug}
              appSlug={app.slug}
              accessToken={accessToken}
            />
          </TabsContent>

          {/* Storage tab */}
          <TabsContent value="storage" className="pt-5">
            <VolumesTab
              tenantSlug={tenantSlug}
              appSlug={app.slug}
              accessToken={accessToken}
            />
          </TabsContent>

          {/* Canary tab */}
          <TabsContent value="canary" className="pt-5">
            <CanaryTab
              tenantSlug={tenantSlug}
              appSlug={app.slug}
              accessToken={accessToken}
            />
          </TabsContent>

          {/* Settings tab */}
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

      {/* Build Modal */}
      <BuildModal
        open={showBuildModal}
        onClose={() => setShowBuildModal(false)}
        onConfirm={handleBuildConfirm}
        loading={actionLoading === "build"}
        appName={app.name}
        currentBranch={app.branch}
        repoUrl={app.repo_url}
        useDockerfile={app.use_dockerfile}
        dockerfilePath={app.dockerfile_path}
      />

      {/* Deploy Modal */}
      <DeployModal
        open={showDeployModal}
        onClose={() => setShowDeployModal(false)}
        onConfirm={handleDeployConfirm}
        loading={actionLoading === "deploy"}
        appName={app.name}
        imageTag={app.image_tag}
        replicas={app.replicas}
        cpuLimit={app.resource_cpu_limit || "500m"}
        memoryLimit={app.resource_memory_limit || "512Mi"}
      />
    </AppShell>
  );
}
