"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useSession } from "next-auth/react";
import { useRouter, useParams } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { api, GitHubRepo, GitHubBranch } from "@/lib/api";
import { ArrowLeft, Loader2, Github, ChevronDown, RefreshCw, CheckCircle } from "lucide-react";

const GITHUB_TOKEN_KEY = "haven_github_oauth_token";

function slugify(s: string) {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 63);
}

export default function NewAppPage() {
  const { data: session } = useSession();
  const router = useRouter();
  const params = useParams();
  const tenantSlug = params.slug as string;

  // Form state
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugManual, setSlugManual] = useState(false);
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("main");
  const [replicas, setReplicas] = useState(1);
  const [dockerfilePath, setDockerfilePath] = useState("");
  const [buildContext, setBuildContext] = useState("");
  const [showMonorepo, setShowMonorepo] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

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
  const [repoFilter, setRepoFilter] = useState("");

  // Session access token from NextAuth GitHub sign-in (fallback)
  const s = session as typeof session & { accessToken?: string; provider?: string };
  const sessionToken = s?.provider === "github" ? s?.accessToken : undefined;

  // Effective token: OAuth popup > NextAuth GitHub session
  const effectiveToken = githubToken ?? sessionToken ?? null;

  // Restore OAuth token from localStorage and validate it
  useEffect(() => {
    const stored = localStorage.getItem(GITHUB_TOKEN_KEY);
    if (stored) {
      // Validate the token by attempting to load repos
      // If it fails, clear it and show reconnect
      setGithubToken(stored);
    }
  }, []);

  // Track the last token that triggered a repo load to detect reconnects
  const lastLoadedTokenRef = useRef<string | null>(null);

  // Auto-load repos when token is available, with retry for newly issued tokens
  const loadRepos = useCallback(async (token: string, retries = 2) => {
    setReposLoading(true);
    setReposError("");
    try {
      const data = await api.github.repos(token);
      setRepos(data);
    } catch (err) {
      if (retries > 0) {
        // Retry after a short delay — new OAuth tokens may need a moment to activate
        await new Promise((r) => setTimeout(r, 1000));
        return loadRepos(token, retries - 1);
      }
      // Token likely expired — clear it so user sees "Reconnect"
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
      // Token was cleared (disconnect) — reset tracking so next token triggers reload
      lastLoadedTokenRef.current = null;
      return;
    }
    // Reload repos when a new/different token arrives, regardless of repos.length
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
        setConnectError("Popup blocked — allow popups for this site and try again");
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
          // Also store the token server-side for this tenant (used for builds)
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

      // Cleanup if popup is closed without completing
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
    // Clear server-side token first — only clear local state on success
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
    // Cancel any in-flight branch request to prevent race conditions
    branchAbortRef.current?.abort();
    const controller = new AbortController();
    branchAbortRef.current = controller;

    setBranchesLoading(true);
    setBranches([]);
    try {
      const [owner, repoName] = repo.full_name.split("/");
      const data = await api.github.branches(owner, repoName, token);
      if (controller.signal.aborted) return; // stale response
      setBranches(data);
      const defaultBranch = data.find((b) => b.name === repo.default_branch) ?? data[0];
      if (defaultBranch) setBranch(defaultBranch.name);
    } catch {
      if (controller.signal.aborted) return;
      // fall through — branch text input still available
    } finally {
      if (!controller.signal.aborted) setBranchesLoading(false);
    }
  }

  function handleSelectRepo(repo: GitHubRepo) {
    setSelectedRepo(repo);
    setRepoUrl(repo.clone_url);
    setBranch(repo.default_branch);
    if (effectiveToken) loadBranches(repo, effectiveToken);
  }

  function handleNameChange(v: string) {
    setName(v);
    if (!slugManual) setSlug(slugify(v));
  }

  function handleSlugChange(v: string) {
    setSlugManual(true);
    setSlug(slugify(v));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !slug.trim() || !repoUrl.trim()) return;

    setLoading(true);
    setError("");
    try {
      await api.apps.create(
        tenantSlug,
        {
          slug,
          name,
          repo_url: repoUrl,
          branch,
          replicas,
          ...(dockerfilePath ? { dockerfile_path: dockerfilePath, use_dockerfile: true } : {}),
          ...(buildContext ? { build_context: buildContext } : {}),
        },
        s?.accessToken
      );
      router.push(`/tenants/${tenantSlug}/apps/${slug}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create application");
    } finally {
      setLoading(false);
    }
  }

  const isConnected = !!effectiveToken;
  const connectedViaSession = !githubToken && !!sessionToken;

  return (
    <AppShell userEmail={session?.user?.email}>
      <div className="p-6 max-w-lg">
        {/* Header */}
        <div className="flex items-center gap-3 mb-8">
          <Link
            href={`/tenants/${tenantSlug}`}
            className="text-gray-400 dark:text-[#555] hover:text-gray-900 dark:hover:text-white transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div>
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
              New Application
            </h1>
            <p className="text-sm text-gray-500 dark:text-[#888] mt-0.5">
              Deploy a new app to{" "}
              <span className="font-mono text-gray-600 dark:text-[#aaa]">{tenantSlug}</span>
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          {/* App identity */}
          <div className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg p-5 space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-[#ccc] mb-1.5">
                Application name
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => handleNameChange(e.target.value)}
                placeholder="My App"
                required
                className="w-full px-3 py-2 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0f0f0f] text-gray-900 dark:text-white text-sm placeholder-gray-400 dark:placeholder-[#444] focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-colors"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-[#ccc] mb-1.5">
                Slug{" "}
                <span className="text-gray-400 dark:text-[#555] font-normal">
                  (auto-generated)
                </span>
              </label>
              <input
                type="text"
                value={slug}
                onChange={(e) => handleSlugChange(e.target.value)}
                placeholder="my-app"
                required
                pattern="^[a-z0-9][a-z0-9-]*[a-z0-9]$"
                className="w-full px-3 py-2 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0f0f0f] text-gray-900 dark:text-white text-sm font-mono placeholder-gray-400 dark:placeholder-[#444] focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-colors"
              />
            </div>
          </div>

          {/* Repository section */}
          <div className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg p-5 space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium text-gray-500 dark:text-[#777] uppercase tracking-wider">
                Repository
              </p>
              <button
                type="button"
                onClick={() => setManualMode(!manualMode)}
                className="text-xs text-blue-500 hover:text-blue-600 transition-colors"
              >
                {manualMode ? "← Use GitHub" : "Enter manually →"}
              </button>
            </div>

            {!manualMode && (
              <>
                {/* GitHub connection status */}
                {isConnected ? (
                  <div className="flex items-center justify-between gap-2 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-md px-3 py-2">
                    <div className="flex items-center gap-2 text-xs text-green-700 dark:text-green-400">
                      <CheckCircle className="w-3.5 h-3.5 flex-shrink-0" />
                      {connectedViaSession ? "Connected via GitHub Sign-In" : "GitHub connected"}
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => effectiveToken && loadRepos(effectiveToken)}
                        disabled={reposLoading}
                        title="Reload repos"
                        className="p-1 rounded hover:bg-green-100 dark:hover:bg-green-900/40 text-green-600 dark:text-green-400 transition-colors disabled:opacity-50"
                      >
                        <RefreshCw className={`w-3 h-3 ${reposLoading ? "animate-spin" : ""}`} />
                      </button>
                      {!connectedViaSession && (
                        <button
                          type="button"
                          onClick={disconnectGitHub}
                          className="text-xs text-red-500 hover:text-red-600 transition-colors"
                        >
                          Disconnect
                        </button>
                      )}
                    </div>
                  </div>
                ) : (
                  /* Connect GitHub button */
                  <div className="space-y-2">
                    <button
                      type="button"
                      onClick={connectGitHub}
                      disabled={connecting}
                      className="w-full flex items-center justify-center gap-2.5 px-4 py-2.5 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0f0f0f] hover:bg-gray-50 dark:hover:bg-[#1a1a1a] text-gray-900 dark:text-white text-sm font-medium transition-colors disabled:opacity-60"
                    >
                      {connecting ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Github className="w-4 h-4" />
                      )}
                      {connecting ? "Waiting for authorization…" : "Connect GitHub"}
                    </button>
                    {connectError && (
                      <p className="text-xs text-red-500 bg-red-500/10 border border-red-500/20 rounded-md px-3 py-2">
                        {connectError}
                      </p>
                    )}
                  </div>
                )}

                {reposError && (
                  <p className="text-xs text-red-500 bg-red-500/10 border border-red-500/20 rounded-md px-3 py-2">
                    {reposError}
                  </p>
                )}

                {/* Repo picker */}
                {isConnected && repos.length > 0 && (
                  <div className="space-y-3">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-[#ccc] mb-1.5">
                        Repository
                        <span className="ml-1.5 text-xs text-gray-400 dark:text-[#555] font-normal">
                          ({repos.length})
                        </span>
                      </label>
                      {repos.length > 10 && (
                        <input
                          type="text"
                          value={repoFilter}
                          onChange={(e) => setRepoFilter(e.target.value)}
                          placeholder="Filter repositories..."
                          className="w-full px-3 py-1.5 mb-1.5 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0f0f0f] text-gray-900 dark:text-white text-xs placeholder-gray-400 dark:placeholder-[#444] focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors"
                        />
                      )}
                      <div className="relative">
                        <select
                          value={selectedRepo?.full_name ?? ""}
                          onChange={(e) => {
                            const repo = repos.find((r) => r.full_name === e.target.value);
                            if (repo) handleSelectRepo(repo);
                          }}
                          className="w-full appearance-none px-3 py-2 pr-8 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0f0f0f] text-gray-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-colors"
                        >
                          <option value="">Select a repository...</option>
                          {repos
                            .filter((r) => !repoFilter || r.full_name.toLowerCase().includes(repoFilter.toLowerCase()))
                            .map((r) => (
                            <option key={r.id} value={r.full_name}>
                              {r.private ? "🔒 " : ""}
                              {r.full_name}
                            </option>
                          ))}
                        </select>
                        <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none" />
                      </div>
                    </div>

                    {selectedRepo && (
                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-[#ccc] mb-1.5">
                          Branch
                          {branchesLoading && (
                            <Loader2 className="inline w-3 h-3 ml-1 animate-spin" />
                          )}
                        </label>
                        {branches.length > 0 ? (
                          <div className="relative">
                            <select
                              value={branch}
                              onChange={(e) => setBranch(e.target.value)}
                              className="w-full appearance-none px-3 py-2 pr-8 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0f0f0f] text-gray-900 dark:text-white text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-colors"
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
                            value={branch}
                            onChange={(e) => setBranch(e.target.value)}
                            placeholder="main"
                            className="w-full px-3 py-2 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0f0f0f] text-gray-900 dark:text-white text-sm font-mono placeholder-gray-400 dark:placeholder-[#444] focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-colors"
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
                    Loading repositories…
                  </div>
                )}
              </>
            )}

            {/* Manual mode */}
            {manualMode && (
              <div className="space-y-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-[#ccc] mb-1.5">
                    GitHub repository URL
                  </label>
                  <input
                    type="url"
                    value={repoUrl}
                    onChange={(e) => setRepoUrl(e.target.value)}
                    placeholder="https://github.com/owner/repo"
                    required
                    className="w-full px-3 py-2 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0f0f0f] text-gray-900 dark:text-white text-sm font-mono placeholder-gray-400 dark:placeholder-[#444] focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-colors"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-[#ccc] mb-1.5">
                    Branch
                  </label>
                  <input
                    type="text"
                    value={branch}
                    onChange={(e) => setBranch(e.target.value)}
                    placeholder="main"
                    required
                    className="w-full px-3 py-2 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0f0f0f] text-gray-900 dark:text-white text-sm font-mono placeholder-gray-400 dark:placeholder-[#444] focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-colors"
                  />
                </div>
              </div>
            )}

            {/* Replicas */}
            <div className="border-t border-gray-100 dark:border-[#1e1e1e] pt-4">
              <label className="block text-sm font-medium text-gray-700 dark:text-[#ccc] mb-1.5">
                Replicas
              </label>
              <input
                type="number"
                min={1}
                max={20}
                value={replicas}
                onChange={(e) => setReplicas(Number(e.target.value))}
                className="w-24 px-3 py-2 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0f0f0f] text-gray-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-colors"
              />
              <p className="text-xs text-gray-400 dark:text-[#555] mt-1.5">
                Number of Kubernetes pod replicas.
              </p>
            </div>
          </div>

          {/* Monorepo settings (collapsible) */}
          <div>
            <button
              type="button"
              onClick={() => setShowMonorepo(!showMonorepo)}
              className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
            >
              <ChevronDown className={`w-3 h-3 transition-transform ${showMonorepo ? "rotate-180" : ""}`} />
              Monorepo Settings (optional)
            </button>
            {showMonorepo && (
              <div className="mt-3 space-y-3 pl-4 border-l-2 border-gray-200 dark:border-gray-700">
                <div>
                  <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                    Dockerfile Path
                  </label>
                  <input
                    type="text"
                    value={dockerfilePath}
                    onChange={(e) => setDockerfilePath(e.target.value)}
                    placeholder="e.g. backend/Dockerfile"
                    className="w-full px-3 py-2 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0f0f0f] text-gray-900 dark:text-white text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                  />
                  <p className="text-xs text-gray-400 dark:text-gray-600 mt-1">
                    Path to Dockerfile relative to repo root. Leave empty for auto-detect.
                  </p>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                    Build Context
                  </label>
                  <input
                    type="text"
                    value={buildContext}
                    onChange={(e) => setBuildContext(e.target.value)}
                    placeholder="e.g. backend"
                    className="w-full px-3 py-2 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0f0f0f] text-gray-900 dark:text-white text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                  />
                  <p className="text-xs text-gray-400 dark:text-gray-600 mt-1">
                    Build root directory relative to repo root. Defaults to repo root.
                  </p>
                </div>
              </div>
            )}
          </div>

          {error && (
            <p className="text-sm text-red-500 bg-red-500/10 border border-red-500/20 rounded-md px-3 py-2">
              {error}
            </p>
          )}

          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={loading || !name.trim() || !slug.trim() || !repoUrl.trim()}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors"
            >
              {loading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              Create application
            </button>
            <Link
              href={`/tenants/${tenantSlug}`}
              className="px-4 py-2 rounded-md text-sm text-gray-500 dark:text-[#888] hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-[#1a1a1a] transition-colors"
            >
              Cancel
            </Link>
          </div>
        </form>
      </div>
    </AppShell>
  );
}
