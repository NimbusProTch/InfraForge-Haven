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
import EnvVarEditor from "@/components/EnvVarEditor";
import { AnsiTerminal } from "@/components/ui/ansi-terminal";
import { BuildModal, DeployModal } from "@/components/BuildDeployModal";
import { ScaleModal } from "@/components/ScaleModal";
import { RestartModal } from "@/components/RestartModal";
import { ConnectedServicesPanel } from "@/components/ConnectedServicesPanel";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import type { AppServiceEntry } from "@/lib/api";
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
  Check,
  X,
  Circle,
  ExternalLink,
  RefreshCw,
  Search,
  Upload,
  Clock,
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

  let statuses: PipelineStepStatus[];
  switch (deployment.status) {
    case "pending":
      statuses = ["pending", "pending", "pending", "pending", "pending"];
      break;
    case "building":
      statuses = ["success", "success", "running", "pending", "pending"];
      break;
    case "built":
      statuses = ["success", "success", "success", "success", "pending"];
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

// ---- Step Icons ----

const STEP_ICONS: Record<string, React.ElementType> = {
  clone: GitBranch,
  detect: Search,
  build: Hammer,
  push: Upload,
  deploy: Rocket,
};

function StepStatusIcon({
  status,
  stepKey,
  size = "md",
}: {
  status: PipelineStepStatus;
  stepKey?: string;
  size?: "sm" | "md";
}) {
  const s = size === "sm" ? "w-7 h-7" : "w-10 h-10";
  const iconSize = size === "sm" ? "w-3.5 h-3.5" : "w-4.5 h-4.5";
  const StepIcon = stepKey ? STEP_ICONS[stepKey] : null;

  if (status === "success") {
    return (
      <div className={`${s} rounded-full bg-emerald-500 flex items-center justify-center shadow-sm transition-all duration-300`}>
        <Check className={`${iconSize} text-white`} strokeWidth={2.5} />
      </div>
    );
  }
  if (status === "running") {
    return (
      <div className={`${s} rounded-full bg-blue-500/10 border-2 border-blue-500 flex items-center justify-center shadow-[0_0_0_4px_rgba(59,130,246,0.15)] transition-all duration-300`}>
        <Loader2 className={`${iconSize} text-blue-500 animate-spin`} />
      </div>
    );
  }
  if (status === "failed") {
    return (
      <div className={`${s} rounded-full bg-red-500 flex items-center justify-center shadow-sm transition-all duration-300`}>
        <X className={`${iconSize} text-white`} strokeWidth={2.5} />
      </div>
    );
  }
  return (
    <div className={`${s} rounded-full border-2 border-dashed border-gray-300 dark:border-zinc-600 bg-transparent flex items-center justify-center transition-all duration-300`}>
      {StepIcon ? (
        <StepIcon className={`${iconSize} text-gray-400 dark:text-zinc-500`} />
      ) : (
        <Circle className={`${size === "sm" ? "w-2.5 h-2.5" : "w-3 h-3"} text-gray-400 dark:text-zinc-500`} />
      )}
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
      <div className="flex items-center w-full">
        {steps.map((step, i) => (
          <div key={step.key} className="flex items-center flex-1 last:flex-none">
            <div className="flex flex-col items-center gap-1.5">
              <StepStatusIcon status={step.status} stepKey={step.key} size="sm" />
              <span className={`text-xs font-medium ${
                step.status === "success" ? "text-emerald-600 dark:text-emerald-400" :
                step.status === "running" ? "text-blue-600 dark:text-blue-400" :
                step.status === "failed" ? "text-red-600 dark:text-red-400" :
                "text-gray-400 dark:text-zinc-500"
              }`}>
                {step.label}
              </span>
            </div>
            {i < steps.length - 1 && (
              <div className="flex-1 mx-2 min-w-3 relative">
                <div className="h-1 rounded-full bg-gray-200 dark:bg-zinc-700" />
                {step.status === "success" && (
                  <div className="absolute top-0 left-0 h-1 rounded-full bg-emerald-500 w-full transition-all duration-500" />
                )}
                {step.status === "failed" && (
                  <div className="absolute top-0 left-0 h-1 rounded-full bg-red-400 w-full" />
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="flex items-center w-full py-2">
      {steps.map((step, i) => {
        const isActive = activeStep === step.key;
        return (
          <div key={step.key} className="flex items-center flex-1 last:flex-none">
            <div
              className={`flex flex-col items-center gap-2 ${
                isClickable && step.status !== "pending" ? "cursor-pointer group" : ""
              }`}
              onClick={() => isClickable && step.status !== "pending" && onStepClick?.(step.key)}
            >
              <div className={`transition-transform duration-200 ${
                isActive ? "scale-110" : ""
              } ${isClickable && step.status !== "pending" ? "group-hover:scale-110" : ""}`}>
                <StepStatusIcon status={step.status} stepKey={step.key} />
              </div>
              <div className="text-center">
                <span className={`text-sm font-semibold block ${
                  step.status === "success" ? "text-emerald-700 dark:text-emerald-400" :
                  step.status === "running" ? "text-blue-700 dark:text-blue-400" :
                  step.status === "failed" ? "text-red-700 dark:text-red-400" :
                  "text-gray-400 dark:text-zinc-500"
                }`}>
                  {step.label}
                </span>
                <span className="text-xs font-medium text-gray-500 dark:text-zinc-500 tabular-nums">
                  {step.duration ?? (step.status === "pending" ? "—" : "")}
                </span>
              </div>
            </div>
            {i < steps.length - 1 && (
              <div className="flex-1 mx-3 min-w-6 relative self-start mt-5">
                <div className="h-1 rounded-full bg-gray-200 dark:bg-zinc-700" />
                {step.status === "success" && (
                  <div className="absolute top-0 left-0 h-1 rounded-full bg-emerald-500 w-full transition-all duration-500 ease-out" />
                )}
                {step.status === "running" && (
                  <div className="absolute top-0 left-0 h-1 rounded-full bg-gradient-to-r from-blue-500 to-blue-300 w-1/2 animate-pulse" />
                )}
                {step.status === "failed" && (
                  <div className="absolute top-0 left-0 h-1 rounded-full bg-red-400 w-full" />
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ---- Status helpers ----

const DEPLOY_STATUS_VARIANT: Record<string, "success" | "warning" | "destructive" | "secondary" | "default"> = {
  running: "success",
  building: "warning",
  built: "default",
  deploying: "warning",
  pending: "secondary",
  failed: "destructive",
};

const STATUS_DOT_COLORS: Record<string, string> = {
  running: "bg-emerald-500",
  building: "bg-amber-500 animate-pulse",
  built: "bg-purple-500",
  deploying: "bg-blue-500 animate-pulse",
  pending: "bg-gray-400",
  failed: "bg-red-500",
};

function relativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

// ---- Deployment Card ----

function DeploymentCard({
  deployment,
  onRollback,
  rolling,
  isFirst,
}: {
  deployment: Deployment;
  onRollback: (id: string) => void;
  rolling: string | null;
  isFirst?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const isActive = ["building", "deploying"].includes(deployment.status);
  const isFailed = deployment.status === "failed";
  const pipelineSteps = derivePipelineSteps(deployment);

  return (
    <div
      className={`border-b border-gray-100 dark:border-zinc-800/60 last:border-0 transition-colors ${
        isActive ? "bg-blue-50 dark:bg-blue-500/5" : ""
      } ${isFirst && deployment.status === "running" ? "border-l-3 border-l-emerald-500" : ""}`}
    >
      <div className="flex items-center justify-between px-5 py-4">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <div className="shrink-0">
            <div className={`w-2.5 h-2.5 rounded-full ${STATUS_DOT_COLORS[deployment.status] ?? "bg-gray-400"}`} />
          </div>
          <div className="min-w-0 shrink-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-mono font-bold text-gray-900 dark:text-white">
                {deployment.commit_sha ? deployment.commit_sha.slice(0, 7) : "manual"}
              </span>
              <Badge variant={DEPLOY_STATUS_VARIANT[deployment.status] ?? "secondary"}>
                {deployment.status}
              </Badge>
            </div>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-xs font-medium text-gray-500 dark:text-zinc-500" title={new Date(deployment.created_at).toLocaleString()}>
                {relativeTime(deployment.created_at)}
              </span>
              {deployment.image_tag && deployment.status === "running" && (
                <span className="text-xs font-mono text-gray-500 dark:text-zinc-500">
                  {deployment.image_tag.split(":").pop()}
                </span>
              )}
            </div>
          </div>

          {(isActive || isFailed || deployment.status === "running" || deployment.status === "built") && (
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
              {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </button>
          )}
          {["running", "failed", "built"].includes(deployment.status) && deployment.image_tag && (
            <button
              onClick={() => onRollback(deployment.id)}
              disabled={rolling === deployment.id}
              title={deployment.status === "built" ? "Deploy this image" : "Rollback to this deployment"}
              className="text-gray-400 dark:text-zinc-600 hover:text-gray-700 dark:hover:text-zinc-300 transition-colors disabled:opacity-50"
            >
              {rolling === deployment.id ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : deployment.status === "built" ? (
                <Rocket className="w-3.5 h-3.5 text-purple-500" />
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
            <pre className="text-xs font-mono text-red-400 whitespace-pre-wrap break-all">{deployment.error_message}</pre>
          </div>
        </div>
      )}

      {(isActive || isFailed || deployment.status === "built") && (
        <div className="md:hidden px-4 pb-3">
          <PipelineVisualization steps={pipelineSteps} compact />
        </div>
      )}
    </div>
  );
}

// ---- Build Log Terminal ----

const STEP_TO_CONTAINER: Record<string, string> = {
  clone: "git-clone",
  detect: "nixpacks",
  build: "buildctl",
};

function parseLogSections(logs: string): Map<string, string> {
  const sections = new Map<string, string>();
  const regex = /^--- (git-clone|nixpacks|buildctl) ---$/m;
  const parts = logs.split(regex);
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
          {onStepFilter && sections.size > 1 && (
            <div className="flex items-center gap-0.5 bg-gray-100 dark:bg-zinc-800 rounded-lg p-0.5">
              {filterTabs.map((tab) => (
                <button
                  key={tab.key ?? "all"}
                  onClick={() => onStepFilter(tab.key)}
                  className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
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
        <AnsiTerminal content={filteredLogs} className="p-4 max-h-[400px]" endRef={endRef} />
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

  const [logs, setLogs] = useState<string>("");
  const [streaming, setStreaming] = useState(false);
  const logsEndRef = useRef<HTMLDivElement>(null);

  const [buildStatus, setBuildStatus] = useState<BuildStatus | null>(null);
  const [activeLogStep, setActiveLogStep] = useState<string | null>(null);
  const [showBuildModal, setShowBuildModal] = useState(false);
  const [showDeployModal, setShowDeployModal] = useState(false);
  const [showScaleModal, setShowScaleModal] = useState(false);
  const [showRestartModal, setShowRestartModal] = useState(false);
  const [appServices, setAppServices] = useState<AppServiceEntry[]>([]);
  const [envVars, setEnvVars] = useState<Record<string, string>>({});
  const [envSaving, setEnvSaving] = useState(false);
  const [logSearch, setLogSearch] = useState("");
  const [activeTab, setActiveTab] = useState("overview");
  const [lastStatusRefresh, setLastStatusRefresh] = useState<Date>(new Date());
  const [refreshingStatus, setRefreshingStatus] = useState(false);
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
    } catch { /* ignore */ }
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
        setEnvVars(a.env_vars ?? {});
        setDeployments(d as Deployment[]);
        api.apps.getServices(tenantSlug, appSlug, accessToken).then(setAppServices).catch(() => {});
      } catch {
        router.push(`/tenants/${tenantSlug}`);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [tenantSlug, appSlug, status, accessToken, router]);

  const loadApp = useCallback(async () => {
    if (status !== "authenticated") return;
    try {
      const a = await api.apps.get(tenantSlug, appSlug, accessToken);
      setApp(a);
    } catch { /* ignore */ }
  }, [tenantSlug, appSlug, status, accessToken]);

  const loadAppServices = useCallback(async () => {
    if (status !== "authenticated") return;
    try {
      const svcs = await api.apps.getServices(tenantSlug, appSlug, accessToken);
      setAppServices(svcs);
    } catch { /* ignore */ }
  }, [tenantSlug, appSlug, status, accessToken]);

  const refreshStatus = useCallback(async () => {
    setRefreshingStatus(true);
    try {
      await Promise.all([loadApp(), loadDeployments()]);
      setLastStatusRefresh(new Date());
    } finally {
      setRefreshingStatus(false);
    }
  }, [loadApp, loadDeployments]);

  const latestDeployment = deployments[0];
  const isActiveBuild =
    latestDeployment != null &&
    ["building", "deploying", "pending"].includes(latestDeployment.status);

  const loadBuildStatus = useCallback(async () => {
    if (status !== "authenticated") return;
    try {
      const bs = await api.deployments.buildStatus(tenantSlug, appSlug, accessToken);
      setBuildStatus(bs);
    } catch { /* ignore */ }
  }, [tenantSlug, appSlug, status, accessToken]);

  useEffect(() => {
    if (isActiveBuild) {
      deployPollRef.current = setInterval(() => {
        loadDeployments();
        loadBuildStatus();
        loadApp();
      }, 5000);
      loadBuildStatus();
    } else {
      setBuildStatus(null);
      setActiveLogStep(null);
      loadApp();
    }
    return () => {
      if (deployPollRef.current) {
        clearInterval(deployPollRef.current);
        deployPollRef.current = null;
      }
    };
  }, [isActiveBuild, loadDeployments, loadBuildStatus, loadApp]);

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

  async function handleSaveEnvVars() {
    setEnvSaving(true);
    try {
      const updated = await api.apps.update(tenantSlug, appSlug, { env_vars: envVars }, accessToken);
      setApp(updated);
      toastSuccess("Variables saved");
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Failed to save variables");
    } finally {
      setEnvSaving(false);
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

  // Compute uptime from latest running deployment
  const uptimeText = (() => {
    if (currentStatus !== "running" || !latestDeployment) return null;
    return relativeTime(latestDeployment.created_at).replace(" ago", "");
  })();

  return (
    <AppShell userEmail={session?.user?.email}>
      <div className="p-6 lg:p-8">
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
            <div className="flex items-center gap-3 mb-1">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 shadow-md flex items-center justify-center shrink-0">
                <Rocket className="w-4.5 h-4.5 text-white" />
              </div>
              <h1 className="text-2xl font-extrabold text-gray-900 dark:text-white tracking-tight">{app.name}</h1>
              {currentStatus && (
                <Badge variant={DEPLOY_STATUS_VARIANT[currentStatus] ?? "secondary"}>
                  {currentStatus}
                </Badge>
              )}
              <button
                onClick={() => void refreshStatus()}
                disabled={refreshingStatus}
                title="Refresh deployment status"
                className="p-1 rounded-md text-gray-400 dark:text-zinc-600 hover:text-gray-600 dark:hover:text-zinc-400 hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${refreshingStatus ? "animate-spin" : ""}`} />
              </button>
              <span className="text-xs text-gray-400 dark:text-zinc-600">
                Updated {relativeTime(lastStatusRefresh.toISOString())}
              </span>
            </div>
            <div className="flex items-center gap-3 mt-1.5 pl-12">
              <p className="text-sm text-gray-600 dark:text-zinc-400 font-medium">
                <span
                  className="hover:text-blue-500 cursor-pointer transition-colors underline-offset-2 hover:underline"
                  onClick={() => window.open(app.repo_url, "_blank")}
                >
                  {app.repo_url.replace("https://github.com/", "").replace(/\.git$/, "")}
                </span>
                <ChevronRight className="inline w-3.5 h-3.5 mx-1 text-gray-400 dark:text-zinc-600" />
                <span className="inline-flex items-center gap-1 text-gray-700 dark:text-zinc-300">
                  <GitBranch className="w-3.5 h-3.5" />
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

          {/* Action buttons: 1 primary + dropdown */}
          <div className="flex items-center gap-1.5 shrink-0">
            <button
              onClick={() => setShowBuildModal(true)}
              disabled={!!actionLoading}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-bold transition-all shadow-lg shadow-emerald-500/25"
            >
              {actionLoading === "build" ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Rocket className="w-3.5 h-3.5" />
              )}
              Build &amp; Deploy
            </button>

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  aria-label="More actions"
                  className="inline-flex items-center justify-center w-10 h-10 rounded-lg border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 hover:bg-gray-50 dark:hover:bg-zinc-700 text-gray-700 dark:text-zinc-200 transition-all shadow-sm"
                >
                  <ChevronDown className="w-4 h-4" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {app.image_tag && (
                  <DropdownMenuItem onClick={() => setShowDeployModal(true)}>
                    <Rocket className="w-4 h-4 text-emerald-500" />
                    Deploy Existing Image
                  </DropdownMenuItem>
                )}
                <DropdownMenuItem onClick={() => setShowScaleModal(true)}>
                  <Layers className="w-4 h-4 text-blue-500" />
                  Scale
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => setShowRestartModal(true)}>
                  <RotateCcw className="w-4 h-4 text-amber-500" />
                  Restart
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => window.open(app.repo_url, "_blank")}>
                  <ExternalLink className="w-4 h-4" />
                  View on GitHub
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
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
            {buildStatus?.containers && buildStatus.containers.length > 0 && (
              <div className="flex items-center gap-3 mt-3 px-1">
                {buildStatus.containers.map((c) => (
                  <div key={c.name} className="flex items-center gap-1.5">
                    <span className={`w-1.5 h-1.5 rounded-full ${
                      c.status === "completed" ? "bg-emerald-500" :
                      c.status === "running" ? "bg-blue-500 animate-pulse" :
                      c.status === "failed" ? "bg-red-500" : "bg-zinc-600"
                    }`} />
                    <span className="text-xs text-gray-500 dark:text-zinc-500 font-mono">{c.name}</span>
                    {c.duration && <span className="text-xs text-gray-400 dark:text-zinc-600">{c.duration}</span>}
                    {c.exit_code !== null && c.exit_code !== 0 && (
                      <span className="text-xs text-red-400">exit {c.exit_code}</span>
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

        {/* Built status banner */}
        {currentStatus === "built" && latestDeployment && (
          <div className="mb-6 bg-purple-50 dark:bg-purple-500/5 border border-purple-200 dark:border-purple-500/20 rounded-xl p-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-purple-500/15 flex items-center justify-center">
                <Package className="w-4 h-4 text-purple-500" />
              </div>
              <div>
                <p className="text-sm font-semibold text-purple-700 dark:text-purple-400">Image built successfully</p>
                <p className="text-xs text-purple-500 dark:text-purple-500/70">
                  {latestDeployment.image_tag ? `Tag: ${latestDeployment.image_tag.split(":").pop()}` : "Ready to deploy"}
                </p>
              </div>
            </div>
            <button
              onClick={() => setShowDeployModal(true)}
              disabled={!!actionLoading}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-gradient-to-r from-purple-500 to-purple-600 hover:from-purple-600 hover:to-purple-700 disabled:opacity-50 text-white text-sm font-bold transition-all shadow-lg shadow-purple-500/25"
            >
              {actionLoading === "deploy" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Rocket className="w-3.5 h-3.5" />}
              Deploy Now
            </button>
          </div>
        )}

        {/* Info cards — 3 customer-relevant cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
          {/* Status card */}
          <div className="bg-white dark:bg-zinc-900 rounded-xl shadow-md border border-gray-100 dark:border-zinc-800 p-4">
            <div className="flex items-center gap-3">
              <div className={`w-10 h-10 rounded-lg shadow-sm flex items-center justify-center shrink-0 ${
                currentStatus === "running" ? "bg-gradient-to-br from-emerald-400 to-emerald-600" :
                currentStatus === "failed" ? "bg-gradient-to-br from-red-400 to-red-600" :
                currentStatus === "building" || currentStatus === "deploying" ? "bg-gradient-to-br from-amber-400 to-amber-600" :
                "bg-gradient-to-br from-gray-400 to-gray-600"
              }`}>
                <Activity className="w-5 h-5 text-white" />
              </div>
              <div className="min-w-0">
                <p className="text-xs font-bold text-gray-500 dark:text-zinc-400 uppercase tracking-wider">Status</p>
                <div className="flex items-center gap-2">
                  <p className="text-base font-bold text-gray-900 dark:text-white capitalize">{currentStatus ?? "—"}</p>
                  {uptimeText && (
                    <span className="text-xs text-gray-400 dark:text-zinc-500">· {uptimeText}</span>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Instances card */}
          <div className="bg-white dark:bg-zinc-900 rounded-xl shadow-md border border-gray-100 dark:border-zinc-800 p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-blue-400 to-blue-600 shadow-sm flex items-center justify-center shrink-0">
                <Layers className="w-5 h-5 text-white" />
              </div>
              <div className="min-w-0">
                <p className="text-xs font-bold text-gray-500 dark:text-zinc-400 uppercase tracking-wider">Instances</p>
                <p className="text-base font-bold text-gray-900 dark:text-white font-mono">{app.replicas} replica{app.replicas !== 1 ? "s" : ""}</p>
              </div>
            </div>
          </div>

          {/* Last Deploy card */}
          <div className="bg-white dark:bg-zinc-900 rounded-xl shadow-md border border-gray-100 dark:border-zinc-800 p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-violet-400 to-violet-600 shadow-sm flex items-center justify-center shrink-0">
                <Clock className="w-5 h-5 text-white" />
              </div>
              <div className="min-w-0">
                <p className="text-xs font-bold text-gray-500 dark:text-zinc-400 uppercase tracking-wider">Last Deploy</p>
                <p className="text-base font-bold text-gray-900 dark:text-white font-mono">
                  {latestDeployment ? (
                    <>
                      {relativeTime(latestDeployment.created_at)}
                      {latestDeployment.commit_sha && (
                        <span className="text-gray-400 dark:text-zinc-500 text-xs ml-1.5">
                          · {latestDeployment.commit_sha.slice(0, 7)}
                        </span>
                      )}
                    </>
                  ) : "—"}
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Provisioning banner */}
        {app.pending_services && app.pending_services.length > 0 && (
          <div className="mb-4 flex items-center gap-3 px-4 py-3 rounded-lg border border-amber-200 dark:border-amber-500/20 bg-amber-50 dark:bg-amber-500/5">
            <Loader2 className="w-4 h-4 text-amber-500 animate-spin shrink-0" />
            <div className="text-sm">
              <span className="font-medium text-amber-700 dark:text-amber-400">Services provisioning: </span>
              <span className="text-amber-600 dark:text-amber-300">
                {app.pending_services.map((s) => `${s.service_name} (${s.service_type})`).join(", ")}
              </span>
              <p className="text-xs text-amber-500 dark:text-amber-500/70 mt-0.5">
                Build is available but deploy may fail without connected services.
              </p>
            </div>
          </div>
        )}

        {/* 6 tabs — enterprise PaaS convention */}
        <Tabs value={activeTab} onValueChange={(v) => {
          setActiveTab(v);
          // Auto-start log streaming when Logs tab is opened
          if (v === "logs" && !streaming && !logs) {
            startLogs();
          }
        }}>
          <TabsList>
            <TabsTrigger value="overview">
              <Activity className="w-3.5 h-3.5 mr-1" />
              Overview
            </TabsTrigger>
            <TabsTrigger value="deployments">
              <Package className="w-3.5 h-3.5 mr-1" />
              Deployments
              {deployments.length > 0 && (
                <span className="ml-1.5 text-xs text-gray-400 dark:text-zinc-600">{deployments.length}</span>
              )}
            </TabsTrigger>
            <TabsTrigger value="variables">
              <Layers className="w-3.5 h-3.5 mr-1" />
              Variables
            </TabsTrigger>
            <TabsTrigger value="logs">
              <Terminal className="w-3.5 h-3.5 mr-1" />
              Logs
            </TabsTrigger>
            <TabsTrigger value="metrics">
              <Activity className="w-3.5 h-3.5 mr-1" />
              Metrics
            </TabsTrigger>
            <TabsTrigger value="settings">
              <Settings className="w-3.5 h-3.5 mr-1" />
              Settings
            </TabsTrigger>
          </TabsList>

          {/* Overview — status, connected services, last deployment */}
          <TabsContent value="overview" className="pt-5 space-y-6">
            {/* Latest deployment summary */}
            {latestDeployment && (
              <div className="bg-white dark:bg-zinc-900 border border-gray-100 dark:border-zinc-800 rounded-xl p-4 shadow-sm">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`w-2.5 h-2.5 rounded-full ${STATUS_DOT_COLORS[latestDeployment.status] ?? "bg-gray-400"}`} />
                    <div>
                      <span className="text-sm font-semibold text-gray-900 dark:text-white">
                        Latest: {latestDeployment.commit_sha ? latestDeployment.commit_sha.slice(0, 7) : "manual"}
                      </span>
                      <span className="ml-2">
                        <Badge variant={DEPLOY_STATUS_VARIANT[latestDeployment.status] ?? "secondary"}>
                          {latestDeployment.status}
                        </Badge>
                      </span>
                    </div>
                  </div>
                  <span className="text-xs text-gray-500 dark:text-zinc-500">{relativeTime(latestDeployment.created_at)}</span>
                </div>
              </div>
            )}

            {/* Connected Services */}
            <ConnectedServicesPanel
              tenantSlug={tenantSlug}
              appSlug={appSlug}
              services={appServices}
              accessToken={accessToken}
              onRefresh={loadAppServices}
            />

            {!latestDeployment && appServices.length === 0 && (
              <div className="text-center py-16 border border-dashed border-gray-200 dark:border-zinc-800 rounded-xl">
                <Rocket className="w-8 h-8 mx-auto mb-2 text-gray-400 dark:text-zinc-700" />
                <p className="text-sm font-medium text-gray-600 dark:text-zinc-400">Ready to deploy</p>
                <p className="text-xs mt-1 text-gray-400 dark:text-zinc-600">Click &quot;Build &amp; Deploy&quot; to get started.</p>
              </div>
            )}
          </TabsContent>

          {/* Deployments — full history, rollback */}
          <TabsContent value="deployments" className="pt-5">
            {deployments.length === 0 ? (
              <div className="text-center py-12 border border-dashed border-gray-200 dark:border-zinc-800 rounded-xl">
                <Package className="w-8 h-8 mx-auto mb-2 text-gray-400 dark:text-zinc-700" />
                <p className="text-sm text-gray-500 dark:text-zinc-500">No deployments yet.</p>
              </div>
            ) : (
              <div className="bg-white dark:bg-zinc-900 border border-gray-100 dark:border-zinc-800 rounded-xl overflow-hidden shadow-md">
                {deployments.map((d, idx) => (
                  <DeploymentCard
                    key={d.id}
                    deployment={d}
                    onRollback={handleRollback}
                    rolling={rolling}
                    isFirst={idx === 0}
                  />
                ))}
              </div>
            )}
          </TabsContent>

          {/* Variables — top-level, most-used config */}
          <TabsContent value="variables" className="pt-5">
            <div className="max-w-2xl space-y-4">
              <div className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-xl p-5">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-1">Environment Variables</h3>
                <p className="text-xs text-gray-400 dark:text-zinc-500 mb-4">
                  Injected into the container at runtime. Changes take effect on the next deployment.
                </p>
                <EnvVarEditor value={envVars} onChange={setEnvVars} />
              </div>
              <button
                onClick={handleSaveEnvVars}
                disabled={envSaving}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium transition-colors"
              >
                {envSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
                Save Variables
              </button>
            </div>
          </TabsContent>

          {/* Logs — auto-stream on tab open, no manual start button */}
          <TabsContent value="logs" className="pt-5 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                {streaming ? (
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-50 dark:bg-emerald-500/10 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                    Live
                  </span>
                ) : logs ? (
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-gray-100 dark:bg-zinc-800 text-xs font-medium text-gray-500 dark:text-zinc-400">
                    Paused
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-gray-100 dark:bg-zinc-800 text-xs font-medium text-gray-500 dark:text-zinc-400">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    Connecting...
                  </span>
                )}
                {streaming && (
                  <button
                    onClick={stopLogs}
                    className="text-xs text-gray-500 dark:text-zinc-500 hover:text-gray-700 dark:hover:text-zinc-300 transition-colors"
                  >
                    Pause
                  </button>
                )}
                {!streaming && logs && (
                  <>
                    <button
                      onClick={startLogs}
                      className="text-xs text-emerald-600 dark:text-emerald-400 hover:text-emerald-700 dark:hover:text-emerald-300 transition-colors font-medium"
                    >
                      Resume
                    </button>
                    <button
                      onClick={() => setLogs("")}
                      className="text-xs text-gray-400 dark:text-zinc-600 hover:text-gray-500 dark:hover:text-zinc-400 transition-colors"
                    >
                      Clear
                    </button>
                  </>
                )}
              </div>
              {/* Search */}
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 dark:text-zinc-600" />
                <input
                  type="text"
                  value={logSearch}
                  onChange={(e) => setLogSearch(e.target.value)}
                  placeholder="Filter logs..."
                  className="pl-8 pr-3 py-1.5 w-56 rounded-lg border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-xs text-gray-800 dark:text-zinc-200 focus:outline-none focus:ring-1 focus:ring-blue-500/50"
                />
              </div>
            </div>

            <div className="bg-zinc-950 border border-gray-200 dark:border-zinc-800 rounded-xl overflow-hidden">
              <div className="flex items-center gap-1.5 px-4 py-2.5 border-b border-gray-200 dark:border-zinc-800">
                <span className="w-2.5 h-2.5 rounded-full bg-red-500/40" />
                <span className="w-2.5 h-2.5 rounded-full bg-amber-500/40" />
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/40" />
                <span className="text-xs text-zinc-700 ml-2 font-mono">{app.name}</span>
                {streaming && (
                  <span className="ml-auto flex items-center gap-1 text-xs text-emerald-500">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                    live
                  </span>
                )}
              </div>
              <AnsiTerminal
                content={
                  logs
                    ? logSearch
                      ? logs.split("\n").filter(line => line.toLowerCase().includes(logSearch.toLowerCase())).join("\n") || "# No matching lines\n"
                      : logs
                    : "# Connecting to log stream...\n"
                }
                className="p-4 min-h-[300px] max-h-[600px]"
                endRef={logsEndRef}
              />
            </div>
          </TabsContent>

          {/* Metrics — pod status, CPU/memory */}
          <TabsContent value="metrics" className="pt-5">
            <ObservabilityTab
              tenantSlug={tenantSlug}
              appSlug={appSlug}
              appName={app.name}
              appImageTag={app.image_tag}
              deployments={deployments}
              logs={logs}
              streaming={streaming}
              onStartLogs={startLogs}
              onStopLogs={stopLogs}
            />
          </TabsContent>

          {/* Settings — flat scrollable, "set once" config */}
          <TabsContent value="settings" className="pt-5">
            <AppSettings
              tenantSlug={tenantSlug}
              app={app}
              accessToken={accessToken}
              onSaved={(updated) => {
                setApp(updated);
                setEnvVars(updated.env_vars ?? {});
              }}
            />
          </TabsContent>
        </Tabs>
      </div>

      {/* Modals */}
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

      <DeployModal
        open={showDeployModal}
        onClose={() => setShowDeployModal(false)}
        onConfirm={handleDeployConfirm}
        loading={actionLoading === "deploy"}
        appName={app.name}
        imageTag={app.image_tag}
        replicas={app.replicas}
        availableImages={
          deployments
            .filter((d) => d.image_tag)
            .reduce<Array<{ tag: string; date: string; commitSha?: string; status?: string }>>((acc, d) => {
              if (!acc.find((i) => i.tag === d.image_tag)) {
                acc.push({ tag: d.image_tag!, date: d.created_at, commitSha: d.commit_sha, status: d.status });
              }
              return acc;
            }, [])
        }
      />

      <ScaleModal
        open={showScaleModal}
        onClose={() => setShowScaleModal(false)}
        tenantSlug={tenantSlug}
        appSlug={appSlug}
        currentReplicas={app.replicas}
        currentCpuRequest={app.resource_cpu_request || "50m"}
        currentCpuLimit={app.resource_cpu_limit || "500m"}
        currentMemoryRequest={app.resource_memory_request || "64Mi"}
        currentMemoryLimit={app.resource_memory_limit || "512Mi"}
        minReplicas={app.min_replicas || 1}
        maxReplicas={app.max_replicas || 5}
        cpuThreshold={app.cpu_threshold || 70}
        accessToken={accessToken}
        onSuccess={() => { void loadApp(); toastSuccess("Scale applied"); }}
      />

      <RestartModal
        open={showRestartModal}
        onClose={() => setShowRestartModal(false)}
        tenantSlug={tenantSlug}
        appSlug={appSlug}
        replicas={app.replicas}
        namespace={`tenant-${tenantSlug}`}
        accessToken={accessToken}
        onSuccess={() => toastSuccess("Restart initiated")}
      />
    </AppShell>
  );
}
