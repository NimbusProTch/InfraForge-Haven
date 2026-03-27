"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { api, type Application, type GitHubRepo, type GitHubBranch, type DetectedDeps as DetectedDepsType } from "@/lib/api";
import EnvVarEditor from "@/components/EnvVarEditor";
import ResourceConfig, { type ResourceValues } from "@/components/ResourceConfig";
import DomainConfig, { type DomainValues } from "@/components/DomainConfig";
import DetectedDeps from "@/components/DetectedDeps";
import {
  Loader2,
  Save,
  Trash2,
  Github,
  ChevronDown,
  RefreshCw,
  CheckCircle,
  FileCode,
  Settings,
  Variable,
  Cpu,
  Globe,
  Layers,
  FolderOpen,
} from "lucide-react";

const GITHUB_TOKEN_KEY = "haven_github_oauth_token";

interface AppSettingsProps {
  tenantSlug: string;
  app: Application;
  accessToken?: string;
  onSaved: (updated: Application) => void;
}

export default function AppSettings({ tenantSlug, app, accessToken, onSaved }: AppSettingsProps) {
  const router = useRouter();

  // Form state -- General tab
  const [editName, setEditName] = useState(app.name);
  const [editRepoUrl, setEditRepoUrl] = useState(app.repo_url);
  const [editBranch, setEditBranch] = useState(app.branch);
  const [editReplicas, setEditReplicas] = useState(app.replicas);
  const [useDockerfile, setUseDockerfile] = useState(app.use_dockerfile ?? false);
  const [dockerfilePath, setDockerfilePath] = useState(app.dockerfile_path ?? "");
  const [buildContext, setBuildContext] = useState(app.build_context ?? "");

  // Environment tab
  const [envVars, setEnvVars] = useState<Record<string, string>>(app.env_vars ?? {});

  // Resources tab
  const [resources, setResources] = useState<ResourceValues>({
    cpu_request: app.resource_cpu_request ?? "100m",
    cpu_limit: app.resource_cpu_limit ?? "500m",
    memory_request: app.resource_memory_request ?? "128Mi",
    memory_limit: app.resource_memory_limit ?? "512Mi",
    min_replicas: app.min_replicas ?? 1,
    max_replicas: app.max_replicas ?? 3,
    cpu_threshold: app.cpu_threshold ?? 70,
  });

  // Domain & Health tab
  const [domainValues, setDomainValues] = useState<DomainValues>({
    custom_domain: app.custom_domain ?? "",
    health_check_path: app.health_check_path ?? "/health",
    health_check_type: "http",
    auto_deploy: app.auto_deploy ?? false,
  });

  // Dependencies tab
  const [detectedDeps, setDetectedDeps] = useState<DetectedDepsType | null>(app.detected_deps ?? null);
  const [depsLoading, setDepsLoading] = useState(false);

  // Save state
  const [saving, setSaving] = useState(false);

  // Delete state
  const [deleting, setDeleting] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState("");

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
  const [manualMode, setManualMode] = useState(false);

  const lastLoadedTokenRef = useRef<string | null>(null);

  // Restore OAuth token from localStorage
  useEffect(() => {
    const stored = localStorage.getItem(GITHUB_TOKEN_KEY);
    if (stored) {
      setGithubToken(stored);
    } else {
      setManualMode(true);
    }
  }, []);

  // Load repos when token is available, with retry for newly issued tokens
  const loadRepos = useCallback(async (token: string, retries = 2) => {
    setReposLoading(true);
    setReposError("");
    try {
      const data = await api.github.repos(token);
      setRepos(data);
      return data;
    } catch (err) {
      if (retries > 0) {
        await new Promise((r) => setTimeout(r, 1000));
        return loadRepos(token, retries - 1);
      }
      setReposError(err instanceof Error ? err.message : "Failed to load repositories");
      return [];
    } finally {
      setReposLoading(false);
    }
  }, []);

  // Auto-load repos when token changes
  useEffect(() => {
    if (!githubToken) {
      lastLoadedTokenRef.current = null;
      return;
    }
    if (githubToken !== lastLoadedTokenRef.current) {
      lastLoadedTokenRef.current = githubToken;
      loadRepos(githubToken).then((loaded) => {
        if (loaded && loaded.length > 0) {
          const match = loaded.find(
            (r) => r.clone_url === app.repo_url || r.html_url === app.repo_url
          );
          if (match) {
            setSelectedRepo(match);
            loadBranches(match, githubToken);
          }
        }
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [githubToken, loadRepos]);

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
          setManualMode(false);
          window.removeEventListener("message", handleMessage);
          try {
            await api.github.connect(tenantSlug, token, accessToken);
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

  function disconnectGitHub() {
    localStorage.removeItem(GITHUB_TOKEN_KEY);
    setGithubToken(null);
    setRepos([]);
    setSelectedRepo(null);
    setBranches([]);
    setReposError("");
    setManualMode(true);
  }

  async function loadBranches(repo: GitHubRepo, token: string) {
    setBranchesLoading(true);
    setBranches([]);
    try {
      const [owner, repoName] = repo.full_name.split("/");
      const data = await api.github.branches(owner, repoName, token);
      setBranches(data);
      const current = data.find((b) => b.name === editBranch);
      if (!current) {
        const defaultBranch = data.find((b) => b.name === repo.default_branch) ?? data[0];
        if (defaultBranch) setEditBranch(defaultBranch.name);
      }
    } catch {
      // fall through
    } finally {
      setBranchesLoading(false);
    }
  }

  function handleSelectRepo(repo: GitHubRepo) {
    setSelectedRepo(repo);
    setEditRepoUrl(repo.clone_url);
    setEditBranch(repo.default_branch);
    if (githubToken) loadBranches(repo, githubToken);
    // Auto-detect dependencies on repo change
    detectDependencies(repo);
  }

  async function detectDependencies(repo?: GitHubRepo) {
    const targetRepo = repo ?? selectedRepo;
    if (!targetRepo || !githubToken) return;
    setDepsLoading(true);
    try {
      const [owner, repoName] = targetRepo.full_name.split("/");
      const deps = await api.github.detect(owner, repoName, editBranch || targetRepo.default_branch, githubToken);
      setDetectedDeps(deps);
    } catch {
      // ignore
    } finally {
      setDepsLoading(false);
    }
  }

  async function handleSaveSettings() {
    setSaving(true);
    try {
      const updated = await api.apps.update(
        tenantSlug,
        app.slug,
        {
          name: editName,
          repo_url: editRepoUrl,
          branch: editBranch,
          replicas: editReplicas,
          env_vars: envVars,
        },
        accessToken
      );
      onSaved(updated);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Update failed");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (deleteConfirm !== app.slug) return;
    setDeleting(true);
    try {
      await api.apps.delete(tenantSlug, app.slug, accessToken);
      router.push(`/tenants/${tenantSlug}`);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Delete failed");
      setDeleting(false);
    }
  }

  const isConnected = !!githubToken;

  return (
    <div className="space-y-6 max-w-2xl">
      <Tabs defaultValue="general">
        <TabsList>
          <TabsTrigger value="general">
            <Settings className="w-3.5 h-3.5 mr-1.5" />
            General
          </TabsTrigger>
          <TabsTrigger value="environment">
            <Variable className="w-3.5 h-3.5 mr-1.5" />
            Environment
          </TabsTrigger>
          <TabsTrigger value="resources">
            <Cpu className="w-3.5 h-3.5 mr-1.5" />
            Resources
          </TabsTrigger>
          <TabsTrigger value="domain">
            <Globe className="w-3.5 h-3.5 mr-1.5" />
            Domain & Health
          </TabsTrigger>
          <TabsTrigger value="dependencies">
            <Layers className="w-3.5 h-3.5 mr-1.5" />
            Dependencies
          </TabsTrigger>
        </TabsList>

        {/* General tab */}
        <TabsContent value="general" className="pt-5">
          <div className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg p-5">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-4">Application Settings</h3>
            <div className="space-y-3">
              {/* Name */}
              <div>
                <label className="block text-xs text-gray-500 dark:text-[#666] mb-1">Name</label>
                <input
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="w-full px-3 py-1.5 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0a0a0a] text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </div>

              {/* Repository section */}
              <div className="border-t border-gray-100 dark:border-[#1e1e1e] pt-3">
                <div className="flex items-center justify-between mb-2">
                  <label className="block text-xs text-gray-500 dark:text-[#666]">Repository</label>
                  <button
                    type="button"
                    onClick={() => setManualMode(!manualMode)}
                    className="text-xs text-blue-500 hover:text-blue-600 transition-colors"
                  >
                    {manualMode ? "Use GitHub" : "Enter manually"}
                  </button>
                </div>

                {!manualMode && (
                  <>
                    {isConnected ? (
                      <div className="flex items-center justify-between gap-2 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-md px-3 py-2 mb-3">
                        <div className="flex items-center gap-2 text-xs text-green-700 dark:text-green-400">
                          <CheckCircle className="w-3.5 h-3.5 flex-shrink-0" />
                          GitHub connected
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => githubToken && loadRepos(githubToken)}
                            disabled={reposLoading}
                            title="Reload repos"
                            className="p-1 rounded hover:bg-green-100 dark:hover:bg-green-900/40 text-green-600 dark:text-green-400 transition-colors disabled:opacity-50"
                          >
                            <RefreshCw className={`w-3 h-3 ${reposLoading ? "animate-spin" : ""}`} />
                          </button>
                          <button
                            type="button"
                            onClick={disconnectGitHub}
                            className="text-xs text-red-500 hover:text-red-600 transition-colors"
                          >
                            Disconnect
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-2 mb-3">
                        <button
                          type="button"
                          onClick={connectGitHub}
                          disabled={connecting}
                          className="w-full flex items-center justify-center gap-2.5 px-4 py-2 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0f0f0f] hover:bg-gray-50 dark:hover:bg-[#1a1a1a] text-gray-900 dark:text-white text-sm font-medium transition-colors disabled:opacity-60"
                        >
                          {connecting ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            <Github className="w-4 h-4" />
                          )}
                          {connecting ? "Waiting for authorization..." : "Connect GitHub"}
                        </button>
                        {connectError && (
                          <p className="text-xs text-red-500 bg-red-500/10 border border-red-500/20 rounded-md px-3 py-2">
                            {connectError}
                          </p>
                        )}
                      </div>
                    )}

                    {reposError && (
                      <p className="text-xs text-red-500 bg-red-500/10 border border-red-500/20 rounded-md px-3 py-2 mb-3">
                        {reposError}
                      </p>
                    )}

                    {isConnected && repos.length > 0 && (
                      <div className="space-y-3">
                        <div>
                          <label className="block text-xs text-gray-500 dark:text-[#666] mb-1">
                            Repository
                          </label>
                          <div className="relative">
                            <select
                              value={selectedRepo?.full_name ?? ""}
                              onChange={(e) => {
                                const repo = repos.find((r) => r.full_name === e.target.value);
                                if (repo) handleSelectRepo(repo);
                              }}
                              className="w-full appearance-none px-3 py-1.5 pr-8 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0a0a0a] text-gray-900 dark:text-white text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors"
                            >
                              <option value="">Select a repository...</option>
                              {repos.map((r) => (
                                <option key={r.id} value={r.full_name}>
                                  {r.private ? "private: " : ""}
                                  {r.full_name}
                                </option>
                              ))}
                            </select>
                            <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none" />
                          </div>
                        </div>

                        {selectedRepo && (
                          <div>
                            <label className="block text-xs text-gray-500 dark:text-[#666] mb-1">
                              Branch
                              {branchesLoading && (
                                <Loader2 className="inline w-3 h-3 ml-1 animate-spin" />
                              )}
                            </label>
                            {branches.length > 0 ? (
                              <div className="relative">
                                <select
                                  value={editBranch}
                                  onChange={(e) => setEditBranch(e.target.value)}
                                  className="w-full appearance-none px-3 py-1.5 pr-8 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0a0a0a] text-gray-900 dark:text-white text-sm font-mono focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors"
                                >
                                  {branches.map((b) => (
                                    <option key={b.name} value={b.name}>
                                      {b.name}
                                    </option>
                                  ))}
                                </select>
                                <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none" />
                              </div>
                            ) : (
                              <input
                                type="text"
                                value={editBranch}
                                onChange={(e) => setEditBranch(e.target.value)}
                                placeholder="main"
                                className="w-full px-3 py-1.5 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0a0a0a] text-sm text-gray-900 dark:text-white font-mono focus:outline-none focus:ring-1 focus:ring-blue-500"
                              />
                            )}
                          </div>
                        )}
                      </div>
                    )}

                    {isConnected && repos.length === 0 && !reposLoading && !reposError && (
                      <p className="text-xs text-gray-400 dark:text-[#555]">
                        No repositories found. Check token permissions.
                      </p>
                    )}

                    {reposLoading && (
                      <div className="flex items-center gap-2 text-xs text-gray-400 dark:text-[#555]">
                        <Loader2 className="w-3 h-3 animate-spin" />
                        Loading repositories...
                      </div>
                    )}
                  </>
                )}

                {manualMode && (
                  <div className="space-y-3">
                    <div>
                      <label className="block text-xs text-gray-500 dark:text-[#666] mb-1">Repository URL</label>
                      <input
                        type="text"
                        value={editRepoUrl}
                        onChange={(e) => setEditRepoUrl(e.target.value)}
                        placeholder="https://github.com/owner/repo"
                        className="w-full px-3 py-1.5 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0a0a0a] text-sm text-gray-900 dark:text-white font-mono focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-500 dark:text-[#666] mb-1">Branch</label>
                      <input
                        type="text"
                        value={editBranch}
                        onChange={(e) => setEditBranch(e.target.value)}
                        placeholder="main"
                        className="w-full px-3 py-1.5 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0a0a0a] text-sm text-gray-900 dark:text-white font-mono focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                    </div>
                  </div>
                )}
              </div>

              {/* Replicas */}
              <div>
                <label className="block text-xs text-gray-500 dark:text-[#666] mb-1">Replicas</label>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={editReplicas}
                  onChange={(e) => setEditReplicas(Math.max(1, Math.min(20, Number(e.target.value))))}
                  className="w-24 px-3 py-1.5 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0a0a0a] text-sm text-gray-900 dark:text-white font-mono focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </div>

              {/* Dockerfile toggle */}
              <div className="border-t border-gray-100 dark:border-[#1e1e1e] pt-3">
                <label className="flex items-center gap-3 cursor-pointer group">
                  <div className="relative">
                    <input
                      type="checkbox"
                      checked={useDockerfile}
                      onChange={(e) => setUseDockerfile(e.target.checked)}
                      className="sr-only peer"
                    />
                    <div className="w-9 h-5 rounded-full bg-gray-200 dark:bg-[#2a2a2a] peer-checked:bg-blue-600 transition-colors" />
                    <div className="absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform peer-checked:translate-x-4" />
                  </div>
                  <div className="flex items-center gap-1.5">
                    <FileCode className="w-3.5 h-3.5 text-gray-400 dark:text-[#666]" />
                    <span className="text-xs text-gray-700 dark:text-[#ccc] group-hover:text-gray-900 dark:group-hover:text-white transition-colors">
                      Use existing Dockerfile
                    </span>
                  </div>
                </label>
                <p className="text-xs text-gray-400 dark:text-[#555] mt-1.5 ml-12">
                  When enabled, the build will use the Dockerfile in the repo instead of Nixpacks auto-detection.
                </p>
              </div>

              {/* Monorepo fields (shown when Dockerfile mode enabled) */}
              {useDockerfile && (
                <div className="border-t border-gray-100 dark:border-[#1e1e1e] pt-3 space-y-3">
                  <div className="flex items-center gap-2 mb-2">
                    <FolderOpen className="w-3.5 h-3.5 text-gray-400 dark:text-[#666]" />
                    <span className="text-xs font-medium text-gray-700 dark:text-[#ccc]">
                      Monorepo Settings
                    </span>
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 dark:text-[#666] mb-1">
                      Dockerfile path
                    </label>
                    <input
                      type="text"
                      value={dockerfilePath}
                      onChange={(e) => setDockerfilePath(e.target.value)}
                      placeholder="Dockerfile (or backend/Dockerfile)"
                      className="w-full px-3 py-1.5 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0a0a0a] text-sm text-gray-900 dark:text-white font-mono focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                    <p className="text-xs text-gray-400 dark:text-[#555] mt-1">
                      Relative path to the Dockerfile from the repo root.
                    </p>
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 dark:text-[#666] mb-1">
                      Build context
                    </label>
                    <input
                      type="text"
                      value={buildContext}
                      onChange={(e) => setBuildContext(e.target.value)}
                      placeholder=". (or ./backend)"
                      className="w-full px-3 py-1.5 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0a0a0a] text-sm text-gray-900 dark:text-white font-mono focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                    <p className="text-xs text-gray-400 dark:text-[#555] mt-1">
                      Build root directory. Defaults to repo root if empty.
                    </p>
                  </div>
                </div>
              )}
            </div>

            <button
              onClick={handleSaveSettings}
              disabled={saving}
              className="mt-4 inline-flex items-center gap-1.5 px-4 py-1.5 rounded-md bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-xs font-medium transition-colors"
            >
              {saving ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Save className="w-3.5 h-3.5" />
              )}
              Save Changes
            </button>
          </div>

          {/* Danger zone */}
          <div className="mt-6 bg-white dark:bg-[#141414] border border-red-300 dark:border-red-900/50 rounded-lg p-5">
            <h3 className="text-sm font-semibold text-red-600 dark:text-red-400 mb-2">Danger Zone</h3>
            <p className="text-xs text-gray-500 dark:text-[#666] mb-3">
              Deleting this application will remove all deployments and K8s resources. This action cannot be undone.
            </p>
            <div className="flex items-end gap-3">
              <div className="flex-1">
                <label className="block text-xs text-gray-500 dark:text-[#666] mb-1">
                  Type <span className="font-mono font-semibold text-gray-700 dark:text-[#ccc]">{app.slug}</span> to confirm
                </label>
                <input
                  type="text"
                  value={deleteConfirm}
                  onChange={(e) => setDeleteConfirm(e.target.value)}
                  placeholder={app.slug}
                  className="w-full px-3 py-1.5 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0a0a0a] text-sm text-gray-900 dark:text-white font-mono focus:outline-none focus:ring-1 focus:ring-red-500"
                />
              </div>
              <button
                onClick={handleDelete}
                disabled={deleting || deleteConfirm !== app.slug}
                className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-md bg-red-600 hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-medium transition-colors shrink-0"
              >
                {deleting ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Trash2 className="w-3.5 h-3.5" />
                )}
                Delete Application
              </button>
            </div>
          </div>
        </TabsContent>

        {/* Environment tab */}
        <TabsContent value="environment" className="pt-5">
          <div className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg p-5">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-4">
              Environment Variables
            </h3>
            <p className="text-xs text-gray-400 dark:text-[#555] mb-4">
              Environment variables are injected into the container at runtime as Kubernetes Secrets.
              Changes take effect on the next deployment.
            </p>
            <EnvVarEditor value={envVars} onChange={setEnvVars} />
          </div>
          <button
            onClick={handleSaveSettings}
            disabled={saving}
            className="mt-4 inline-flex items-center gap-1.5 px-4 py-1.5 rounded-md bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-xs font-medium transition-colors"
          >
            {saving ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Save className="w-3.5 h-3.5" />
            )}
            Save Changes
          </button>
        </TabsContent>

        {/* Resources tab */}
        <TabsContent value="resources" className="pt-5">
          <ResourceConfig value={resources} onChange={setResources} />
          <button
            onClick={handleSaveSettings}
            disabled={saving}
            className="mt-4 inline-flex items-center gap-1.5 px-4 py-1.5 rounded-md bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-xs font-medium transition-colors"
          >
            {saving ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Save className="w-3.5 h-3.5" />
            )}
            Save Changes
          </button>
        </TabsContent>

        {/* Domain & Health tab */}
        <TabsContent value="domain" className="pt-5">
          <DomainConfig
            value={domainValues}
            onChange={setDomainValues}
            currentHostname={app.custom_domain || `${app.slug}.${tenantSlug}.sslip.io`}
          />
          <button
            onClick={handleSaveSettings}
            disabled={saving}
            className="mt-4 inline-flex items-center gap-1.5 px-4 py-1.5 rounded-md bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-xs font-medium transition-colors"
          >
            {saving ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Save className="w-3.5 h-3.5" />
            )}
            Save Changes
          </button>
        </TabsContent>

        {/* Dependencies tab */}
        <TabsContent value="dependencies" className="pt-5">
          <DetectedDeps deps={detectedDeps} loading={depsLoading} />
          {selectedRepo && githubToken && (
            <button
              type="button"
              onClick={() => detectDependencies()}
              disabled={depsLoading}
              className="mt-4 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-gray-200 dark:border-[#2e2e2e] text-gray-700 dark:text-[#ccc] text-xs font-medium hover:bg-gray-50 dark:hover:bg-[#1a1a1a] transition-colors disabled:opacity-50"
            >
              {depsLoading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <RefreshCw className="w-3.5 h-3.5" />
              )}
              Re-analyze
            </button>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
