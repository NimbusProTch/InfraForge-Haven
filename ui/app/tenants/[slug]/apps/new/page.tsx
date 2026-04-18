"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useSession } from "next-auth/react";
import { useRouter, useParams } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { GitHubRepoPicker } from "@/components/GitHubRepoPicker";
import { GitHubFileBrowser } from "@/components/GitHubFileBrowser";
import { GiteaRepoSelector } from "@/components/GiteaRepoSelector";
import EnvVarEditor from "@/components/EnvVarEditor";
import { api, GitHubRepo, GitHubBranch, GiteaRepo } from "@/lib/api";
import {
  ArrowLeft,
  ArrowRight,
  Loader2,
  Github,
  ChevronDown,
  RefreshCw,
  CheckCircle,
  Globe,
  Cog,
  Rocket,
  Server,
  Clock,
  Layers,
  FileCode,
  FolderOpen,
  Check,
  Zap,
  Shield,
  Cpu,
  Heart,
  Database,
  X,
} from "lucide-react";
import { ServiceIcon } from "@/components/icons/ServiceIcons";

const GITHUB_TOKEN_KEY = "haven_github_oauth_token";

const STEPS = [
  { number: 1, label: "Identity", icon: Layers },
  { number: 2, label: "Source Code", icon: Github },
  { number: 3, label: "Build", icon: Cog },
  { number: 4, label: "Runtime", icon: Rocket },
  { number: 5, label: "Services", icon: Database },
];

const SERVICE_TYPES = [
  { type: "postgres" as const, label: "PostgreSQL", description: "Relational database with ACID compliance" },
  { type: "mysql" as const, label: "MySQL", description: "Popular relational database" },
  { type: "mongodb" as const, label: "MongoDB", description: "Flexible document database" },
  { type: "redis" as const, label: "Redis", description: "In-memory cache and data store" },
  { type: "rabbitmq" as const, label: "RabbitMQ", description: "Message broker for async processing" },
] as const;

interface SelectedService {
  service_type: "postgres" | "mysql" | "mongodb" | "redis" | "rabbitmq";
  name: string;
  tier: "dev" | "prod";
}

const APP_TYPES = [
  {
    value: "web" as const,
    label: "Web Server",
    description: "HTTP server with external traffic routing and health checks",
    icon: Globe,
  },
  {
    value: "worker" as const,
    label: "Background Worker",
    description: "Long-running process for queue consumption or async tasks",
    icon: Server,
  },
  {
    value: "cronjob" as const,
    label: "Cron Job",
    description: "Scheduled task that runs periodically on a defined schedule",
    icon: Clock,
  },
];

const PORT_PRESETS = [3000, 5000, 8000, 8080];

const RESOURCE_TIERS = [
  {
    id: "starter" as const,
    label: "Starter",
    description: "Good for development",
    cpuRequest: "100m",
    cpuLimit: "200m",
    memRequest: "128Mi",
    memLimit: "256Mi",
    icon: Zap,
  },
  {
    id: "standard" as const,
    label: "Standard",
    description: "Recommended for production",
    cpuRequest: "500m",
    cpuLimit: "1000m",
    memRequest: "512Mi",
    memLimit: "1Gi",
    icon: Shield,
  },
  {
    id: "performance" as const,
    label: "Performance",
    description: "High-traffic applications",
    cpuRequest: "1000m",
    cpuLimit: "2000m",
    memRequest: "1Gi",
    memLimit: "2Gi",
    icon: Cpu,
  },
];

function slugify(s: string) {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 63);
}

// ─── Step Validation ────────────────────────────────────────────────

interface StepErrors {
  name?: string;
  slug?: string;
  repoUrl?: string;
  port?: string;
}

function validateStep1(name: string, slug: string): StepErrors {
  const errors: StepErrors = {};
  if (!name.trim()) errors.name = "Application name is required";
  if (!slug.trim()) {
    errors.slug = "Slug is required";
  } else if (slug.length < 2) {
    errors.slug = "Slug must be at least 2 characters";
  } else if (!/^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/.test(slug)) {
    errors.slug = "Slug must start and end with a letter or number";
  }
  return errors;
}

function validateStep2(repoUrl: string, manualMode: boolean): StepErrors {
  const errors: StepErrors = {};
  if (!repoUrl.trim()) {
    errors.repoUrl = manualMode ? "Repository URL is required" : "Select a repository";
  }
  return errors;
}

function validateStep3(port: number): StepErrors {
  const errors: StepErrors = {};
  if (!port || port < 1 || port > 65535) {
    errors.port = "Port must be between 1 and 65535";
  }
  return errors;
}

// ─── Component ──────────────────────────────────────────────────────

export default function NewAppPage() {
  const { data: session } = useSession();
  const router = useRouter();
  const params = useParams();
  const tenantSlug = params.slug as string;

  // Wizard state
  const [currentStep, setCurrentStep] = useState(1);
  const [errors, setErrors] = useState<StepErrors>({});
  const [showReview, setShowReview] = useState(false);

  // Step 1 — Identity
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugManual, setSlugManual] = useState(false);
  const [appType, setAppType] = useState<"web" | "worker" | "cronjob">("web");

  // Step 2 — Source
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("main");
  const [manualMode, setManualMode] = useState(false);
  // Source picker: "github" (default), "gitea" (self-hosted tenant org), or "manual" URL
  const [sourceType, setSourceType] = useState<"github" | "gitea" | "manual">("github");
  const [giteaRepos, setGiteaRepos] = useState<GiteaRepo[]>([]);
  const [giteaReposLoading, setGiteaReposLoading] = useState(false);
  const [giteaReposError, setGiteaReposError] = useState("");
  const [selectedGiteaRepo, setSelectedGiteaRepo] = useState<GiteaRepo | null>(null);

  // Step 3 — Build
  const [autoDetect, setAutoDetect] = useState(true);
  const [useDockerfile, setUseDockerfile] = useState(false);
  const [dockerfilePath, setDockerfilePath] = useState("");
  const [buildContext, setBuildContext] = useState("");
  const [port, setPort] = useState(8000);

  // Step 4 — Runtime
  const [envVars, setEnvVars] = useState<Record<string, string>>({});
  const [replicas, setReplicas] = useState(1);
  const [customDomain, setCustomDomain] = useState("");
  const [healthCheckPath, setHealthCheckPath] = useState("/health");
  const [resourceTierId, setResourceTierId] = useState<"starter" | "standard" | "performance">("standard");

  // Step 5 — Connect existing services
  const [selectedServices, setSelectedServices] = useState<SelectedService[]>([]);
  const [tenantServices, setTenantServices] = useState<Array<{ name: string; service_type: string; tier: string; status: string }>>([]);
  const [tenantServicesLoading, setTenantServicesLoading] = useState(false);
  const [selectedServiceNames, setSelectedServiceNames] = useState<string[]>([]);

  // Submit state
  const [loading, setLoading] = useState(false);
  const [submitError, setSubmitError] = useState("");

  // GitHub OAuth state
  const [githubToken, setGithubToken] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [connectError, setConnectError] = useState("");

  // Repo/branch state
  const [repos, setRepos] = useState<GitHubRepo[]>([]);
  const [reposLoading, setReposLoading] = useState(false);
  const [reposError, setReposError] = useState("");
  const [selectedRepo, setSelectedRepo] = useState<GitHubRepo | null>(null);
  const [branches, setBranches] = useState<GitHubBranch[]>([]);
  const [branchesLoading, setBranchesLoading] = useState(false);

  // Session access token
  const s = session as typeof session & { accessToken?: string; provider?: string };
  const accessToken = s?.accessToken;
  const sessionToken = s?.provider === "github" ? s?.accessToken : undefined;
  const effectiveToken = githubToken ?? sessionToken ?? null;
  const isConnected = !!effectiveToken;
  const connectedViaSession = !githubToken && !!sessionToken;

  // Derived: owner/repo for file browser
  const repoOwner = selectedRepo ? selectedRepo.full_name.split("/")[0] : "";
  const repoName = selectedRepo ? selectedRepo.full_name.split("/")[1] : "";

  // ── GitHub OAuth logic (unchanged) ──

  useEffect(() => {
    const stored = localStorage.getItem(GITHUB_TOKEN_KEY);
    if (stored) setGithubToken(stored);
  }, []);

  const lastLoadedTokenRef = useRef<string | null>(null);

  const loadRepos = useCallback(async (token: string, retries = 2) => {
    setReposLoading(true);
    setReposError("");
    try {
      const data = await api.github.repos(token);
      setRepos(data);
    } catch (err) {
      if (retries > 0) {
        await new Promise((r) => setTimeout(r, 1000));
        return loadRepos(token, retries - 1);
      }
      const msg = err instanceof Error ? err.message : "Failed to load repositories";
      if (msg.includes("401") || msg.includes("403") || msg.includes("Unauthorized")) {
        localStorage.removeItem(GITHUB_TOKEN_KEY);
        setGithubToken(null);
        setReposError("GitHub token expired. Please reconnect.");
      } else {
        setReposError(msg);
      }
    } finally {
      setReposLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!effectiveToken) {
      lastLoadedTokenRef.current = null;
      return;
    }
    if (effectiveToken !== lastLoadedTokenRef.current) {
      lastLoadedTokenRef.current = effectiveToken;
      loadRepos(effectiveToken);
    }
  }, [effectiveToken, loadRepos]);

  async function connectGitHub() {
    setConnecting(true);
    setConnectError("");
    try {
      const { url } = await api.github.authUrl();
      const popup = window.open(url, "github_oauth", "width=600,height=700,scrollbars=yes,resizable=yes");
      if (!popup) {
        setConnectError("Popup blocked -- allow popups for this site and try again");
        setConnecting(false);
        return;
      }
      const handleMessage = async (e: MessageEvent) => {
        if (e.origin !== window.location.origin) return;
        if (e.data?.type === "github_oauth_success") {
          const token = e.data.access_token as string;
          localStorage.setItem(GITHUB_TOKEN_KEY, token);
          setGithubToken(token);
          setConnecting(false);
          window.removeEventListener("message", handleMessage);
          try {
            await api.github.connect(tenantSlug, token, s?.accessToken);
          } catch (err) {
            console.warn("Failed to store GitHub token server-side:", err);
          }
        } else if (e.data?.type === "github_oauth_error") {
          setConnectError(e.data.error || "GitHub authorization failed");
          setConnecting(false);
          window.removeEventListener("message", handleMessage);
        }
      };
      window.addEventListener("message", handleMessage);
      const pollClosed = setInterval(() => {
        if (popup.closed) {
          clearInterval(pollClosed);
          setConnecting(false);
          window.removeEventListener("message", handleMessage);
        }
      }, 500);
    } catch (err) {
      setConnectError(err instanceof Error ? err.message : "Failed to get GitHub auth URL");
      setConnecting(false);
    }
  }

  async function disconnectGitHub() {
    try {
      await api.github.disconnect(tenantSlug, s?.accessToken);
    } catch (err) {
      setReposError(err instanceof Error ? err.message : "Failed to disconnect. Please try again.");
      return;
    }
    localStorage.removeItem(GITHUB_TOKEN_KEY);
    setGithubToken(null);
    setRepos([]);
    setSelectedRepo(null);
    setBranches([]);
    setRepoUrl("");
    setBranch("main");
    setReposError("");
  }

  const branchAbortRef = useRef<AbortController | null>(null);

  async function loadBranches(repo: GitHubRepo, token: string) {
    branchAbortRef.current?.abort();
    const controller = new AbortController();
    branchAbortRef.current = controller;
    setBranchesLoading(true);
    setBranches([]);
    try {
      const [owner, repoName] = repo.full_name.split("/");
      const data = await api.github.branches(owner, repoName, token);
      if (controller.signal.aborted) return;
      setBranches(data);
      const defaultBranch = data.find((b) => b.name === repo.default_branch) ?? data[0];
      if (defaultBranch) setBranch(defaultBranch.name);
    } catch {
      if (controller.signal.aborted) return;
    } finally {
      if (!controller.signal.aborted) setBranchesLoading(false);
    }
  }

  function handleSelectRepo(repo: GitHubRepo | null) {
    if (!repo) {
      setSelectedRepo(null);
      setRepoUrl("");
      setBranch("main");
      setBranches([]);
      return;
    }
    setSelectedRepo(repo);
    setRepoUrl(repo.clone_url);
    setBranch(repo.default_branch);
    if (effectiveToken) loadBranches(repo, effectiveToken);
  }

  // ── Name/Slug handlers ──

  function handleNameChange(v: string) {
    setName(v);
    if (!slugManual) {
      const s = slugify(v);
      setSlug(s);
    }
    setErrors((prev) => ({ ...prev, name: undefined }));
  }

  function handleSlugChange(v: string) {
    setSlugManual(true);
    setSlug(slugify(v));
    setErrors((prev) => ({ ...prev, slug: undefined }));
  }

  // ── Navigation ──

  function goNext() {
    let stepErrors: StepErrors = {};
    if (currentStep === 1) stepErrors = validateStep1(name, slug);
    if (currentStep === 2) stepErrors = validateStep2(repoUrl, manualMode);
    if (currentStep === 3) stepErrors = validateStep3(port);

    if (Object.keys(stepErrors).length > 0) {
      setErrors(stepErrors);
      return;
    }
    setErrors({});

    if (currentStep === 5) {
      setShowReview(true);
      return;
    }
    const nextStep = Math.min(currentStep + 1, 5);
    // Load tenant services when entering Step 5
    if (nextStep === 5 && tenantServices.length === 0) {
      setTenantServicesLoading(true);
      api.services.list(tenantSlug, accessToken)
        .then((svcs) => setTenantServices(svcs as unknown as typeof tenantServices))
        .catch(() => {})
        .finally(() => setTenantServicesLoading(false));
    }
    setCurrentStep(nextStep);
  }

  function goPrev() {
    if (showReview) {
      setShowReview(false);
      return;
    }
    setErrors({});
    setCurrentStep((p) => Math.max(p - 1, 1));
  }

  // ── Submit ──

  const selectedResourceTier = RESOURCE_TIERS.find((t) => t.id === resourceTierId)!;

  async function handleSubmit(buildAfterCreate: boolean) {
    setLoading(true);
    setSubmitError("");
    try {
      const body = {
        slug,
        name,
        repo_url: repoUrl,
        branch,
        replicas,
        port,
        app_type: appType,
        env_vars: envVars,
        ...(customDomain ? { custom_domain: customDomain } : {}),
        health_check_path: healthCheckPath || "/health",
        resource_cpu_request: selectedResourceTier.cpuRequest,
        resource_cpu_limit: selectedResourceTier.cpuLimit,
        resource_memory_request: selectedResourceTier.memRequest,
        resource_memory_limit: selectedResourceTier.memLimit,
        ...(useDockerfile ? { use_dockerfile: true } : {}),
        ...(dockerfilePath ? { dockerfile_path: dockerfilePath } : {}),
        ...(buildContext ? { build_context: buildContext } : {}),
        ...(selectedServiceNames.length > 0
          ? { connect_services: selectedServiceNames }
          : {}),
      };

      const app = await api.apps.create(tenantSlug, body, accessToken);
      if (buildAfterCreate) {
        try {
          await api.deployments.build(tenantSlug, app.slug, accessToken);
        } catch (err) {
          console.warn("Build trigger failed:", err);
        }
      }
      router.push(`/tenants/${tenantSlug}/apps/${app.slug}`);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Failed to create application");
    } finally {
      setLoading(false);
    }
  }

  // ── Shared Styles ──

  const inputClass =
    "w-full px-3.5 py-2.5 rounded-lg border border-gray-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 text-gray-900 dark:text-white text-sm placeholder-gray-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 transition-colors shadow-sm";
  const labelClass = "block text-sm font-semibold text-gray-800 dark:text-zinc-200 mb-1.5";
  const errorClass = "text-xs text-red-500 mt-1.5 font-medium";
  const cardBase =
    "bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-xl p-6 shadow-sm";

  // ── Render ──

  return (
    <AppShell userEmail={session?.user?.email}>
      <div className="p-6 max-w-2xl mx-auto">
        {/* Header */}
        <div className="flex items-center gap-3 mb-8">
          <Link
            href={`/tenants/${tenantSlug}`}
            className="text-gray-400 dark:text-[#555] hover:text-gray-900 dark:hover:text-white transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">New Application</h1>
            <p className="text-sm text-gray-500 dark:text-[#888] mt-0.5">
              Deploy a new app to{" "}
              <span className="font-mono text-gray-600 dark:text-[#aaa]">{tenantSlug}</span>
            </p>
          </div>
        </div>

        {/* ── Progress Bar ── */}
        <div className="mb-8">
          <div className="flex items-center justify-between relative">
            {/* Connecting line */}
            <div className="absolute top-5 left-0 right-0 h-0.5 bg-gray-200 dark:bg-[#222]" />
            <div
              className="absolute top-5 left-0 h-0.5 bg-blue-500 transition-all duration-300"
              style={{
                width: showReview
                  ? "100%"
                  : `${((currentStep - 1) / (STEPS.length - 1)) * 100}%`,
              }}
            />

            {STEPS.map((step) => {
              const isActive = currentStep === step.number;
              const isCompleted = currentStep > step.number || showReview;
              const Icon = step.icon;
              return (
                <div key={step.number} className="relative flex flex-col items-center z-10">
                  <button
                    type="button"
                    onClick={() => {
                      if (isCompleted && !showReview) {
                        setCurrentStep(step.number);
                        setErrors({});
                      }
                    }}
                    disabled={!isCompleted || showReview}
                    className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-semibold transition-all duration-200 ${
                      isCompleted
                        ? "bg-blue-500 text-white shadow-md shadow-blue-500/25"
                        : isActive
                          ? "bg-blue-500 text-white shadow-md shadow-blue-500/25 ring-4 ring-blue-500/20"
                          : "bg-white dark:bg-[#1a1a1a] text-gray-400 dark:text-[#555] border-2 border-gray-200 dark:border-[#333]"
                    }`}
                  >
                    {isCompleted && !isActive ? (
                      <Check className="w-4 h-4" />
                    ) : (
                      <Icon className="w-4 h-4" />
                    )}
                  </button>
                  <span
                    className={`mt-2 text-xs font-medium ${
                      isActive || isCompleted
                        ? "text-blue-600 dark:text-blue-400"
                        : "text-gray-400 dark:text-[#555]"
                    }`}
                  >
                    {step.label}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* ── Step 1: Identity ── */}
        {currentStep === 1 && !showReview && (
          <div className={cardBase}>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">
              App Identity
            </h2>
            <p className="text-sm text-gray-500 dark:text-[#888] mb-6">
              Give your application a name. A URL-safe slug will be auto-generated.
            </p>

            <div className="space-y-5">
              {/* Name */}
              <div>
                <label className={labelClass}>Application Name</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => handleNameChange(e.target.value)}
                  placeholder="My Application"
                  autoFocus
                  className={`${inputClass} text-base py-3 ${errors.name ? "border-red-400 dark:border-red-500/50 focus:ring-red-500/40" : ""}`}
                />
                {errors.name && <p className={errorClass}>{errors.name}</p>}
              </div>

              {/* Slug */}
              <div>
                <label className={labelClass}>
                  Slug{" "}
                  <span className="text-gray-400 dark:text-[#555] font-normal">(auto-generated)</span>
                </label>
                <input
                  type="text"
                  value={slug}
                  onChange={(e) => handleSlugChange(e.target.value)}
                  placeholder="my-application"
                  className={`${inputClass} font-mono ${errors.slug ? "border-red-400 dark:border-red-500/50 focus:ring-red-500/40" : ""}`}
                />
                {errors.slug && <p className={errorClass}>{errors.slug}</p>}
                {!errors.slug && slug && (
                  <p className="text-xs text-gray-400 dark:text-[#555] mt-1">
                    Your app will be available as{" "}
                    <span className="font-mono text-gray-600 dark:text-[#aaa]">{slug}</span>
                  </p>
                )}
              </div>

              {/* App Type removed — defaults to "web". Worker/cron can be set later from app settings. */}
            </div>
          </div>
        )}

        {/* ── Step 2: Source Code ── */}
        {currentStep === 2 && !showReview && (
          <div className={cardBase}>
            <div className="mb-1">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Source Code</h2>
            </div>
            <p className="text-sm text-gray-500 dark:text-[#888] mb-4">
              Pick a repository from GitHub, your tenant&apos;s self-hosted Gitea, or paste a URL.
            </p>

            {/* 3-way source picker */}
            <div
              role="tablist"
              aria-label="Source type"
              className="inline-flex rounded-lg border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-900 p-1 mb-6"
            >
              {(
                [
                  { id: "github", label: "GitHub" },
                  { id: "gitea", label: "Gitea (self-hosted)" },
                  { id: "manual", label: "Manual URL" },
                ] as const
              ).map((tab) => (
                <button
                  key={tab.id}
                  role="tab"
                  type="button"
                  aria-selected={sourceType === tab.id}
                  data-testid={`source-tab-${tab.id}`}
                  onClick={() => {
                    setSourceType(tab.id);
                    setManualMode(tab.id === "manual");
                    // Clear stale repoUrl on tab switch so the user has to
                    // re-select from the new source
                    if (tab.id !== "manual") {
                      setRepoUrl("");
                    }
                  }}
                  className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors ${
                    sourceType === tab.id
                      ? "bg-white dark:bg-zinc-800 text-gray-900 dark:text-white shadow-sm"
                      : "text-gray-500 dark:text-zinc-400 hover:text-gray-700 dark:hover:text-zinc-200"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            <div className="space-y-4">
              {sourceType === "github" && (
                <>
                  {/* GitHub connection */}
                  {isConnected ? (
                    <div className="flex items-center justify-between gap-3 rounded-xl border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-800/50 px-4 py-3 shadow-sm">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-lg bg-gray-900 dark:bg-white flex items-center justify-center">
                          <Github className="w-5 h-5 text-white dark:text-gray-900" />
                        </div>
                        <div>
                          <p className="text-sm font-medium text-gray-900 dark:text-zinc-100">
                            {connectedViaSession ? "GitHub Sign-In" : "GitHub Connected"}
                          </p>
                          <p className="text-xs text-gray-400 dark:text-zinc-500">
                            Repository access granted
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => effectiveToken && loadRepos(effectiveToken)}
                          disabled={reposLoading}
                          title="Refresh repositories"
                          className="p-2 rounded-lg text-gray-400 hover:text-gray-600 dark:text-zinc-500 dark:hover:text-zinc-300 hover:bg-gray-100 dark:hover:bg-zinc-700 transition-colors disabled:opacity-50"
                        >
                          <RefreshCw className={`w-4 h-4 ${reposLoading ? "animate-spin" : ""}`} />
                        </button>
                        {!connectedViaSession && (
                          <button
                            type="button"
                            onClick={disconnectGitHub}
                            title="Disconnect GitHub"
                            className="p-2 rounded-lg text-gray-400 hover:text-red-500 dark:text-zinc-500 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                          >
                            <X className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <button
                        type="button"
                        onClick={connectGitHub}
                        disabled={connecting}
                        className="w-full flex items-center justify-center gap-2.5 px-4 py-3 rounded-lg border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0f0f0f] hover:bg-gray-50 dark:hover:bg-[#1a1a1a] text-gray-900 dark:text-white text-sm font-medium transition-colors disabled:opacity-60"
                      >
                        {connecting ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <Github className="w-4 h-4" />
                        )}
                        {connecting ? "Waiting for authorization..." : "Connect GitHub"}
                      </button>
                      {connectError && (
                        <p className="text-xs text-red-500 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                          {connectError}
                        </p>
                      )}
                    </div>
                  )}

                  {reposError && (
                    <p className="text-xs text-red-500 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                      {reposError}
                    </p>
                  )}

                  {/* Repo picker */}
                  {isConnected && (
                    <div className="space-y-4">
                      <div>
                        <label className={labelClass}>Repository</label>
                        <GitHubRepoPicker
                          repos={repos}
                          loading={reposLoading}
                          selected={selectedRepo}
                          onSelect={handleSelectRepo}
                          onRefresh={() => effectiveToken && loadRepos(effectiveToken)}
                        />
                        {errors.repoUrl && !repoUrl && (
                          <p className={errorClass}>{errors.repoUrl}</p>
                        )}
                      </div>

                      {/* Branch */}
                      {selectedRepo && (
                        <div>
                          <label className={labelClass}>
                            Branch
                            {branchesLoading && (
                              <Loader2 className="inline w-3 h-3 ml-1.5 animate-spin" />
                            )}
                          </label>
                          {branches.length > 0 ? (
                            <div className="relative">
                              <select
                                value={branch}
                                onChange={(e) => setBranch(e.target.value)}
                                className={`${inputClass} appearance-none pr-8 font-mono`}
                              >
                                {branches.map((b) => (
                                  <option key={b.name} value={b.name}>
                                    {b.name}
                                  </option>
                                ))}
                              </select>
                              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
                            </div>
                          ) : (
                            <input
                              type="text"
                              value={branch}
                              onChange={(e) => setBranch(e.target.value)}
                              placeholder="main"
                              className={`${inputClass} font-mono`}
                            />
                          )}
                        </div>
                      )}
                    </div>
                  )}

                  {reposLoading && repos.length === 0 && (
                    <div className="flex items-center gap-2 text-sm text-gray-400 dark:text-[#555] py-4 justify-center">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Loading repositories...
                    </div>
                  )}

                  {/* Org-repo visibility hint — OAuth App approval is a GitHub-side
                      setting that org owners must toggle; nothing we can fix in code.
                      Surface it so the operator knows where to look. */}
                  {isConnected && !reposLoading && repos.length > 0 && (
                    <div
                      data-testid="github-org-approval-hint"
                      className="text-xs text-gray-500 dark:text-zinc-400 bg-gray-50 dark:bg-zinc-900/50 border border-gray-200 dark:border-zinc-700 rounded-lg px-3 py-2"
                    >
                      Not seeing repos from one of your organizations? An org owner
                      must approve the <strong>iyziops</strong> OAuth App at{" "}
                      <code className="font-mono text-gray-600 dark:text-zinc-300">
                        github.com/organizations/&lt;org&gt;/settings/oauth_application_policy
                      </code>
                      .
                    </div>
                  )}
                </>
              )}

              {/* Gitea (self-hosted tenant org) */}
              {sourceType === "gitea" && (
                <GiteaRepoSelector
                  tenantSlug={tenantSlug}
                  accessToken={accessToken}
                  repos={giteaRepos}
                  loading={giteaReposLoading}
                  error={giteaReposError}
                  selected={selectedGiteaRepo}
                  branch={branch}
                  onBranchChange={setBranch}
                  onLoad={async () => {
                    if (!accessToken) return;
                    setGiteaReposLoading(true);
                    setGiteaReposError("");
                    try {
                      const result = await api.gitea.listRepos(tenantSlug, accessToken);
                      setGiteaRepos(result);
                    } catch (err) {
                      setGiteaReposError(
                        err instanceof Error ? err.message : "Failed to load Gitea repos"
                      );
                    } finally {
                      setGiteaReposLoading(false);
                    }
                  }}
                  onSelect={(repo) => {
                    setSelectedGiteaRepo(repo);
                    setRepoUrl(repo ? repo.clone_url : "");
                    setBranch(repo ? repo.default_branch : "main");
                  }}
                />
              )}

              {/* Manual mode */}
              {sourceType === "manual" && (
                <div className="space-y-4">
                  <div>
                    <label className={labelClass}>GitHub Repository URL</label>
                    <input
                      type="url"
                      value={repoUrl}
                      onChange={(e) => {
                        setRepoUrl(e.target.value);
                        setErrors((prev) => ({ ...prev, repoUrl: undefined }));
                      }}
                      placeholder="https://github.com/owner/repo"
                      className={`${inputClass} font-mono ${errors.repoUrl ? "border-red-400 dark:border-red-500/50" : ""}`}
                    />
                    {errors.repoUrl && <p className={errorClass}>{errors.repoUrl}</p>}
                  </div>
                  <div>
                    <label className={labelClass}>Branch</label>
                    <input
                      type="text"
                      value={branch}
                      onChange={(e) => setBranch(e.target.value)}
                      placeholder="main"
                      className={`${inputClass} font-mono`}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Step 3: Build Configuration ── */}
        {currentStep === 3 && !showReview && (
          <div className={cardBase}>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">
              Build Configuration
            </h2>
            <p className="text-sm text-gray-500 dark:text-[#888] mb-6">
              Configure how your application is built and which port it listens on.
            </p>

            <div className="space-y-6">
              {/* Auto-detect toggle */}
              <div className="flex items-center justify-between p-4 rounded-lg border border-gray-200 dark:border-[#2e2e2e] bg-gray-50 dark:bg-[#0f0f0f]">
                <div className="flex items-center gap-3">
                  <Cog className="w-5 h-5 text-gray-500 dark:text-[#888]" />
                  <div>
                    <p className="text-sm font-medium text-gray-900 dark:text-white">
                      Auto-detect framework
                    </p>
                    <p className="text-xs text-gray-500 dark:text-[#777]">
                      Uses Nixpacks to detect language and build configuration
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setAutoDetect(!autoDetect);
                    if (!autoDetect) {
                      setUseDockerfile(false);
                      setDockerfilePath("");
                    }
                  }}
                  className={`relative w-11 h-6 rounded-full transition-colors ${
                    autoDetect ? "bg-blue-500" : "bg-gray-300 dark:bg-[#333]"
                  }`}
                >
                  <span
                    className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${
                      autoDetect ? "translate-x-5" : ""
                    }`}
                  />
                </button>
              </div>

              {/* Use Dockerfile toggle */}
              <div className="flex items-center justify-between p-4 rounded-lg border border-gray-200 dark:border-[#2e2e2e] bg-gray-50 dark:bg-[#0f0f0f]">
                <div className="flex items-center gap-3">
                  <FileCode className="w-5 h-5 text-gray-500 dark:text-[#888]" />
                  <div>
                    <p className="text-sm font-medium text-gray-900 dark:text-white">
                      Use existing Dockerfile
                    </p>
                    <p className="text-xs text-gray-500 dark:text-[#777]">
                      Build using a Dockerfile from your repository
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={useDockerfile}
                  aria-label="Use existing Dockerfile"
                  onClick={() => {
                    setUseDockerfile(!useDockerfile);
                    if (!useDockerfile) {
                      setAutoDetect(false);
                    } else {
                      setDockerfilePath("");
                    }
                  }}
                  className={`relative w-11 h-6 rounded-full transition-colors ${
                    useDockerfile ? "bg-blue-500" : "bg-gray-300 dark:bg-[#333]"
                  }`}
                >
                  <span
                    className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${
                      useDockerfile ? "translate-x-5" : ""
                    }`}
                  />
                </button>
              </div>

              {/* Dockerfile picker */}
              {useDockerfile && selectedRepo && effectiveToken && (
                <div>
                  <label className={labelClass}>
                    <FileCode className="inline w-3.5 h-3.5 mr-1.5 -mt-0.5" />
                    Dockerfile Path
                  </label>
                  <GitHubFileBrowser
                    owner={repoOwner}
                    repo={repoName}
                    branch={branch}
                    token={effectiveToken}
                    mode="file"
                    placeholder="Select a Dockerfile..."
                    value={dockerfilePath}
                    onSelect={setDockerfilePath}
                  />
                </div>
              )}

              {useDockerfile && !selectedRepo && (
                <div>
                  <label className={labelClass}>Dockerfile Path</label>
                  <input
                    type="text"
                    value={dockerfilePath}
                    onChange={(e) => setDockerfilePath(e.target.value)}
                    placeholder="e.g. backend/Dockerfile"
                    className={`${inputClass} font-mono`}
                  />
                </div>
              )}

              {/* Build context */}
              <div>
                <label className={labelClass}>
                  <FolderOpen className="inline w-3.5 h-3.5 mr-1.5 -mt-0.5" />
                  Build Context
                  <span className="text-gray-400 dark:text-[#555] font-normal ml-1">(optional)</span>
                </label>
                {selectedRepo && effectiveToken ? (
                  <GitHubFileBrowser
                    owner={repoOwner}
                    repo={repoName}
                    branch={branch}
                    token={effectiveToken}
                    mode="directory"
                    placeholder="Repository root (default)"
                    value={buildContext}
                    onSelect={setBuildContext}
                  />
                ) : (
                  <input
                    type="text"
                    value={buildContext}
                    onChange={(e) => setBuildContext(e.target.value)}
                    placeholder="e.g. backend"
                    className={`${inputClass} font-mono`}
                  />
                )}
                <p className="text-xs text-gray-400 dark:text-[#555] mt-1.5">
                  Build root directory relative to repo root. Defaults to repo root.
                </p>
              </div>

              {/* Port */}
              <div>
                <label className={labelClass}>Application Port</label>
                <div className="flex items-center gap-3">
                  <input
                    type="number"
                    min={1}
                    max={65535}
                    value={port}
                    onChange={(e) => {
                      setPort(Number(e.target.value));
                      setErrors((prev) => ({ ...prev, port: undefined }));
                    }}
                    className={`w-28 ${inputClass} ${errors.port ? "border-red-400 dark:border-red-500/50" : ""}`}
                  />
                  <div className="flex items-center gap-1.5">
                    {PORT_PRESETS.map((p) => (
                      <button
                        key={p}
                        type="button"
                        onClick={() => {
                          setPort(p);
                          setErrors((prev) => ({ ...prev, port: undefined }));
                        }}
                        className={`px-2.5 py-1.5 rounded-md text-xs font-mono font-medium transition-colors ${
                          port === p
                            ? "bg-blue-500 text-white"
                            : "bg-gray-100 dark:bg-[#1a1a1a] text-gray-600 dark:text-[#999] hover:bg-gray-200 dark:hover:bg-[#222]"
                        }`}
                      >
                        {p}
                      </button>
                    ))}
                  </div>
                </div>
                {errors.port && <p className={errorClass}>{errors.port}</p>}
              </div>
            </div>
          </div>
        )}

        {/* ── Step 4: Runtime & Deploy ── */}
        {currentStep === 4 && !showReview && (
          <div className={cardBase}>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">
              Runtime & Deploy
            </h2>
            <p className="text-sm text-gray-500 dark:text-[#888] mb-6">
              Configure environment, scaling, and resource allocation.
            </p>

            <div className="space-y-6">
              {/* Environment Variables */}
              <div>
                <label className={labelClass}>Environment Variables</label>
                <EnvVarEditor value={envVars} onChange={setEnvVars} />
              </div>

              {/* Replicas */}
              <div>
                <label className={labelClass}>Replicas</label>
                <div className="flex items-center gap-3">
                  <input
                    type="number"
                    min={1}
                    max={20}
                    value={replicas}
                    onChange={(e) => setReplicas(Math.min(20, Math.max(1, Number(e.target.value))))}
                    className={`w-24 ${inputClass}`}
                  />
                  <p className="text-xs text-gray-400 dark:text-[#555]">
                    Number of Kubernetes pod replicas (1-20)
                  </p>
                </div>
              </div>

              {/* Custom Domain */}
              <div>
                <label className={labelClass}>
                  Custom Domain
                  <span className="text-gray-400 dark:text-[#555] font-normal ml-1">(optional)</span>
                </label>
                <input
                  type="text"
                  value={customDomain}
                  onChange={(e) => setCustomDomain(e.target.value)}
                  placeholder="e.g. api.myapp.com"
                  className={inputClass}
                />
              </div>

              {/* Health Check Path */}
              <div>
                <label className={labelClass}>
                  <Heart className="inline w-3.5 h-3.5 mr-1.5 -mt-0.5" />
                  Health Check Path
                </label>
                <input
                  type="text"
                  value={healthCheckPath}
                  onChange={(e) => setHealthCheckPath(e.target.value)}
                  placeholder="/health"
                  className={`${inputClass} font-mono`}
                />
                <p className="text-xs text-gray-400 dark:text-[#555] mt-1.5">
                  HTTP endpoint for liveness and readiness probes
                </p>
              </div>

              {/* Resource Tier */}
              <div>
                <label className={labelClass}>Resource Tier</label>
                <div className="grid grid-cols-3 gap-3 mt-2">
                  {RESOURCE_TIERS.map((tier) => {
                    const Icon = tier.icon;
                    const isSelected = resourceTierId === tier.id;
                    return (
                      <button
                        key={tier.id}
                        type="button"
                        onClick={() => setResourceTierId(tier.id)}
                        className={`relative flex flex-col items-center gap-2 p-4 rounded-xl border-2 transition-all duration-200 text-center ${
                          isSelected
                            ? "border-blue-500 bg-blue-50 dark:bg-blue-500/10 shadow-sm"
                            : "border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0f0f0f] hover:border-gray-300 dark:hover:border-[#444]"
                        }`}
                      >
                        {isSelected && (
                          <div className="absolute top-2 right-2">
                            <Check className="w-3.5 h-3.5 text-blue-500" />
                          </div>
                        )}
                        <div
                          className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                            isSelected
                              ? "bg-blue-500 text-white"
                              : "bg-gray-100 dark:bg-[#1a1a1a] text-gray-500 dark:text-[#888]"
                          }`}
                        >
                          <Icon className="w-5 h-5" />
                        </div>
                        <span
                          className={`text-sm font-semibold ${
                            isSelected ? "text-blue-700 dark:text-blue-400" : "text-gray-900 dark:text-white"
                          }`}
                        >
                          {tier.label}
                        </span>
                        <div className="text-[11px] text-gray-500 dark:text-[#777] leading-tight">
                          <p>{tier.cpuRequest} CPU, {tier.memRequest} RAM</p>
                        </div>
                        <span className="text-[10px] text-gray-400 dark:text-[#666]">
                          {tier.description}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── Step 5: Connect Services ── */}
        {currentStep === 5 && !showReview && (
          <div className={cardBase}>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">
              Connect Services
            </h2>
            <p className="text-sm text-gray-500 dark:text-zinc-400 mb-6">
              Select existing managed services to connect to your application.
              Connection details will be injected as environment variables.
            </p>

            {tenantServicesLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
              </div>
            ) : tenantServices.length === 0 ? (
              <div className="text-center py-10 border border-dashed border-gray-200 dark:border-zinc-700 rounded-xl bg-gray-50/50 dark:bg-zinc-800/30">
                <Database className="w-8 h-8 mx-auto mb-3 text-gray-300 dark:text-zinc-600" />
                <p className="text-sm font-medium text-gray-600 dark:text-zinc-400 mb-1">
                  No managed services yet
                </p>
                <p className="text-xs text-gray-400 dark:text-zinc-500 mb-4 max-w-sm mx-auto">
                  Create databases, caches, or message brokers from the project&apos;s Services tab first, then connect them here.
                </p>
                <Link
                  href={`/tenants/${tenantSlug}`}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium transition-colors"
                >
                  <Database className="w-3.5 h-3.5" />
                  Go to Project Services
                </Link>
              </div>
            ) : (
              <div className="space-y-2">
                {tenantServices.map((svc) => {
                  const isSelected = selectedServiceNames.includes(svc.name);
                  const statusColor = svc.status === "ready"
                    ? "bg-emerald-500"
                    : svc.status === "provisioning"
                      ? "bg-amber-500 animate-pulse"
                      : "bg-red-500";
                  return (
                    <button
                      key={svc.name}
                      type="button"
                      onClick={() => {
                        if (isSelected) {
                          setSelectedServiceNames((prev) => prev.filter((n) => n !== svc.name));
                        } else {
                          setSelectedServiceNames((prev) => [...prev, svc.name]);
                        }
                      }}
                      className={`w-full flex items-center gap-4 p-4 rounded-xl border-2 text-left transition-all ${
                        isSelected
                          ? "border-blue-500 bg-blue-50/50 dark:bg-blue-500/10 shadow-sm"
                          : "border-gray-200 dark:border-zinc-700 hover:border-gray-300 dark:hover:border-zinc-600"
                      }`}
                    >
                      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                        isSelected ? "bg-blue-100 dark:bg-blue-500/20" : "bg-gray-100 dark:bg-zinc-800"
                      }`}>
                        <ServiceIcon type={svc.service_type} size={24} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-sm text-gray-900 dark:text-white">{svc.name}</span>
                          <span className={`w-2 h-2 rounded-full ${statusColor}`} />
                          <span className="text-xs text-gray-400 dark:text-zinc-500 capitalize">{svc.status}</span>
                        </div>
                        <div className="flex items-center gap-2 mt-0.5 text-xs text-gray-500 dark:text-zinc-500">
                          <span className="capitalize">{svc.service_type}</span>
                          <span className="text-gray-300 dark:text-zinc-700">·</span>
                          <span>{svc.tier}</span>
                        </div>
                      </div>
                      <div className={`w-5 h-5 rounded-md border-2 flex items-center justify-center transition-colors ${
                        isSelected
                          ? "border-blue-500 bg-blue-500"
                          : "border-gray-300 dark:border-zinc-600"
                      }`}>
                        {isSelected && <Check className="w-3 h-3 text-white" />}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}

            {selectedServiceNames.length > 0 && (
              <div className="mt-4 p-3 rounded-lg bg-blue-50 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20">
                <p className="text-xs text-blue-700 dark:text-blue-400 font-medium">
                  {selectedServiceNames.length} service{selectedServiceNames.length > 1 ? "s" : ""} will be connected after app creation.
                  {tenantServices.some((s) => selectedServiceNames.includes(s.name) && s.status === "provisioning") && (
                    <span className="block mt-1 text-amber-600 dark:text-amber-400">
                      Services still provisioning will be auto-connected when ready.
                    </span>
                  )}
                </p>
              </div>
            )}

            {tenantServices.length > 0 && selectedServiceNames.length === 0 && (
              <p className="text-center text-sm text-gray-400 dark:text-zinc-600 py-3 mt-2">
                No services selected — you can connect them later from the app detail page.
              </p>
            )}
          </div>
        )}

        {/* ── Review ── */}
        {showReview && (
          <div className={cardBase}>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">
              Review & Create
            </h2>
            <p className="text-sm text-gray-500 dark:text-[#888] mb-6">
              Review your application configuration before creating.
            </p>

            <div className="space-y-4">
              {/* Identity */}
              <div className="p-4 rounded-lg bg-gray-50 dark:bg-[#0f0f0f] border border-gray-100 dark:border-[#1e1e1e]">
                <h3 className="text-xs font-semibold text-gray-500 dark:text-[#777] uppercase tracking-wider mb-3">
                  Identity
                </h3>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <span className="text-gray-400 dark:text-[#666]">Name</span>
                    <p className="font-medium text-gray-900 dark:text-white">{name}</p>
                  </div>
                  <div>
                    <span className="text-gray-400 dark:text-[#666]">Slug</span>
                    <p className="font-medium font-mono text-gray-900 dark:text-white">{slug}</p>
                  </div>
                  <div>
                    <span className="text-gray-400 dark:text-[#666]">Type</span>
                    <p className="font-medium text-gray-900 dark:text-white">
                      {APP_TYPES.find((t) => t.value === appType)?.label}
                    </p>
                  </div>
                </div>
              </div>

              {/* Source */}
              <div className="p-4 rounded-lg bg-gray-50 dark:bg-[#0f0f0f] border border-gray-100 dark:border-[#1e1e1e]">
                <h3 className="text-xs font-semibold text-gray-500 dark:text-[#777] uppercase tracking-wider mb-3">
                  Source Code
                </h3>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div className="col-span-2">
                    <span className="text-gray-400 dark:text-[#666]">Repository</span>
                    <p className="font-medium font-mono text-gray-900 dark:text-white truncate text-xs">
                      {repoUrl}
                    </p>
                  </div>
                  <div>
                    <span className="text-gray-400 dark:text-[#666]">Branch</span>
                    <p className="font-medium font-mono text-gray-900 dark:text-white">{branch}</p>
                  </div>
                </div>
              </div>

              {/* Build */}
              <div className="p-4 rounded-lg bg-gray-50 dark:bg-[#0f0f0f] border border-gray-100 dark:border-[#1e1e1e]">
                <h3 className="text-xs font-semibold text-gray-500 dark:text-[#777] uppercase tracking-wider mb-3">
                  Build
                </h3>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <span className="text-gray-400 dark:text-[#666]">Mode</span>
                    <p className="font-medium text-gray-900 dark:text-white">
                      {useDockerfile ? "Dockerfile" : autoDetect ? "Auto-detect (Nixpacks)" : "Manual"}
                    </p>
                  </div>
                  <div>
                    <span className="text-gray-400 dark:text-[#666]">Port</span>
                    <p className="font-medium font-mono text-gray-900 dark:text-white">{port}</p>
                  </div>
                  {dockerfilePath && (
                    <div className="col-span-2">
                      <span className="text-gray-400 dark:text-[#666]">Dockerfile</span>
                      <p className="font-medium font-mono text-xs text-gray-900 dark:text-white">
                        {dockerfilePath}
                      </p>
                    </div>
                  )}
                  {buildContext && (
                    <div className="col-span-2">
                      <span className="text-gray-400 dark:text-[#666]">Build Context</span>
                      <p className="font-medium font-mono text-xs text-gray-900 dark:text-white">
                        {buildContext}
                      </p>
                    </div>
                  )}
                </div>
              </div>

              {/* Runtime */}
              <div className="p-4 rounded-lg bg-gray-50 dark:bg-[#0f0f0f] border border-gray-100 dark:border-[#1e1e1e]">
                <h3 className="text-xs font-semibold text-gray-500 dark:text-[#777] uppercase tracking-wider mb-3">
                  Runtime
                </h3>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <span className="text-gray-400 dark:text-[#666]">Replicas</span>
                    <p className="font-medium text-gray-900 dark:text-white">{replicas}</p>
                  </div>
                  <div>
                    <span className="text-gray-400 dark:text-[#666]">Resources</span>
                    <p className="font-medium text-gray-900 dark:text-white">
                      {selectedResourceTier.label} ({selectedResourceTier.cpuRequest} / {selectedResourceTier.memRequest})
                    </p>
                  </div>
                  {customDomain && (
                    <div>
                      <span className="text-gray-400 dark:text-[#666]">Domain</span>
                      <p className="font-medium font-mono text-gray-900 dark:text-white">{customDomain}</p>
                    </div>
                  )}
                  <div>
                    <span className="text-gray-400 dark:text-[#666]">Health Check</span>
                    <p className="font-medium font-mono text-gray-900 dark:text-white">{healthCheckPath || "/health"}</p>
                  </div>
                  <div>
                    <span className="text-gray-400 dark:text-[#666]">Env Vars</span>
                    <p className="font-medium text-gray-900 dark:text-white">
                      {Object.keys(envVars).length} defined
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Connected services review */}
            {selectedServiceNames.length > 0 && (
              <div className="border border-gray-100 dark:border-[#1e1e1e] rounded-xl p-5">
                <h3 className="text-sm font-semibold text-gray-500 dark:text-[#999] uppercase tracking-wider mb-3 flex items-center gap-2">
                  <Database className="w-4 h-4" /> Connected Services
                </h3>
                <div className="space-y-2">
                  {selectedServiceNames.map((svcName) => {
                    const svc = tenantServices.find((s) => s.name === svcName);
                    return (
                      <div key={svcName} className="flex items-center gap-3">
                        <ServiceIcon type={svc?.service_type ?? "postgres"} size={20} />
                        <span className="font-mono text-sm text-gray-900 dark:text-white">{svcName}</span>
                        <span className="text-xs text-gray-400 dark:text-zinc-500 capitalize">{svc?.service_type}</span>
                        <span className={`w-2 h-2 rounded-full ${svc?.status === "ready" ? "bg-emerald-500" : "bg-amber-500"}`} />
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {submitError && (
              <p className="text-sm text-red-500 bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3 mt-4">
                {submitError}
              </p>
            )}

            {/* Submit actions */}
            <div className="flex items-center gap-3 mt-6 pt-6 border-t border-gray-100 dark:border-[#1e1e1e]">
              <button
                type="button"
                onClick={() => handleSubmit(false)}
                disabled={loading}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-gray-900 dark:bg-white hover:bg-gray-800 dark:hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed text-white dark:text-gray-900 text-sm font-semibold transition-colors"
              >
                {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                Create Application
              </button>
              <button
                type="button"
                onClick={() => handleSubmit(true)}
                disabled={loading}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors"
              >
                {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                <Rocket className="w-4 h-4" />
                Create & Build
              </button>
            </div>
          </div>
        )}

        {/* ── Navigation Buttons ── */}
        {!showReview && (
          <div className="flex items-center justify-between mt-6">
            <div>
              {currentStep > 1 ? (
                <button
                  type="button"
                  onClick={goPrev}
                  className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm text-gray-600 dark:text-[#999] hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-[#1a1a1a] transition-colors font-medium"
                >
                  <ArrowLeft className="w-4 h-4" />
                  Previous
                </button>
              ) : (
                <Link
                  href={`/tenants/${tenantSlug}`}
                  className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm text-gray-600 dark:text-[#999] hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-[#1a1a1a] transition-colors font-medium"
                >
                  Cancel
                </Link>
              )}
            </div>
            <button
              type="button"
              onClick={goNext}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold transition-colors"
            >
              {currentStep === 5 ? "Review" : "Next"}
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Back from review */}
        {showReview && (
          <div className="mt-4">
            <button
              type="button"
              onClick={goPrev}
              disabled={loading}
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm text-gray-600 dark:text-[#999] hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-[#1a1a1a] transition-colors font-medium disabled:opacity-50"
            >
              <ArrowLeft className="w-4 h-4" />
              Back to editing
            </button>
          </div>
        )}
      </div>
    </AppShell>
  );
}
