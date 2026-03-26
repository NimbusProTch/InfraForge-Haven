"use client";

import { useState, useEffect, useRef } from "react";
import { useSession } from "next-auth/react";
import { useRouter, useParams } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { api, GitHubRepo, GitHubBranch } from "@/lib/api";
import { ArrowLeft, Loader2, Github, ChevronDown, RefreshCw } from "lucide-react";

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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // GitHub PAT flow
  const [pat, setPat] = useState("");
  const [patSaved, setPatSaved] = useState(false);
  const [repos, setRepos] = useState<GitHubRepo[]>([]);
  const [reposLoading, setReposLoading] = useState(false);
  const [reposError, setReposError] = useState("");
  const [selectedRepo, setSelectedRepo] = useState<GitHubRepo | null>(null);
  const [branches, setBranches] = useState<GitHubBranch[]>([]);
  const [branchesLoading, setBranchesLoading] = useState(false);
  const [manualMode, setManualMode] = useState(false);

  const patInputRef = useRef<HTMLInputElement>(null);

  // Session access token (GitHub OAuth)
  const s = session as typeof session & { accessToken?: string; provider?: string };
  const sessionPat = s?.provider === "github" ? s?.accessToken : undefined;
  const effectivePat = sessionPat ?? (patSaved ? pat : "");

  // Auto-load repos if signed in via GitHub OAuth
  useEffect(() => {
    if (sessionPat && repos.length === 0) {
      loadRepos(sessionPat);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionPat]);

  // Restore PAT from localStorage
  useEffect(() => {
    const stored = localStorage.getItem("haven_github_pat");
    if (stored) {
      setPat(stored);
      setPatSaved(true);
    }
  }, []);

  async function loadRepos(token: string) {
    setReposLoading(true);
    setReposError("");
    try {
      const data = await api.github.repos(token);
      setRepos(data);
    } catch (err) {
      setReposError(err instanceof Error ? err.message : "Failed to load repositories");
    } finally {
      setReposLoading(false);
    }
  }

  async function loadBranches(repo: GitHubRepo, token: string) {
    setBranchesLoading(true);
    setBranches([]);
    try {
      const [owner, repoName] = repo.full_name.split("/");
      const data = await api.github.branches(owner, repoName, token);
      setBranches(data);
      const defaultBranch = data.find((b) => b.name === repo.default_branch) ?? data[0];
      if (defaultBranch) setBranch(defaultBranch.name);
    } catch {
      // fall through — branch input still available
    } finally {
      setBranchesLoading(false);
    }
  }

  function handleSavePat() {
    if (!pat.trim()) return;
    localStorage.setItem("haven_github_pat", pat.trim());
    setPatSaved(true);
    loadRepos(pat.trim());
  }

  function handleClearPat() {
    localStorage.removeItem("haven_github_pat");
    setPat("");
    setPatSaved(false);
    setRepos([]);
    setSelectedRepo(null);
    setBranches([]);
    setRepoUrl("");
    setBranch("main");
    setTimeout(() => patInputRef.current?.focus(), 50);
  }

  function handleSelectRepo(repo: GitHubRepo) {
    setSelectedRepo(repo);
    setRepoUrl(repo.clone_url);
    setBranch(repo.default_branch);
    loadBranches(repo, effectivePat);
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
        { slug, name, repo_url: repoUrl, branch, replicas },
        s?.accessToken
      );
      router.push(`/tenants/${tenantSlug}/apps/${slug}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create application");
    } finally {
      setLoading(false);
    }
  }

  const showGitHubSection = !manualMode;
  const hasToken = !!effectivePat;
  const hasRepos = repos.length > 0;

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

            {showGitHubSection && (
              <>
                {/* GitHub OAuth already connected */}
                {sessionPat ? (
                  <div className="flex items-center gap-2 text-xs text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-md px-3 py-2">
                    <Github className="w-3.5 h-3.5" />
                    Connected via GitHub OAuth
                  </div>
                ) : (
                  /* PAT input */
                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-gray-700 dark:text-[#ccc]">
                      GitHub Personal Access Token
                    </label>
                    {patSaved ? (
                      <div className="flex items-center gap-2">
                        <div className="flex-1 px-3 py-2 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-gray-50 dark:bg-[#0a0a0a] text-gray-400 dark:text-[#555] text-sm font-mono">
                          ghp_••••••••••••••••
                        </div>
                        <button
                          type="button"
                          onClick={() => loadRepos(pat)}
                          disabled={reposLoading}
                          title="Reload repos"
                          className="p-2 rounded-md border border-gray-200 dark:border-[#2e2e2e] hover:bg-gray-100 dark:hover:bg-[#1a1a1a] text-gray-500 dark:text-[#888] transition-colors disabled:opacity-50"
                        >
                          <RefreshCw className={`w-3.5 h-3.5 ${reposLoading ? "animate-spin" : ""}`} />
                        </button>
                        <button
                          type="button"
                          onClick={handleClearPat}
                          className="text-xs text-red-500 hover:text-red-600 transition-colors px-2 py-2"
                        >
                          Clear
                        </button>
                      </div>
                    ) : (
                      <div className="flex gap-2">
                        <input
                          ref={patInputRef}
                          type="password"
                          value={pat}
                          onChange={(e) => setPat(e.target.value)}
                          onKeyDown={(e) =>
                            e.key === "Enter" && (e.preventDefault(), handleSavePat())
                          }
                          placeholder="ghp_..."
                          className="flex-1 px-3 py-2 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0f0f0f] text-gray-900 dark:text-white text-sm font-mono placeholder-gray-400 dark:placeholder-[#444] focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-colors"
                        />
                        <button
                          type="button"
                          onClick={handleSavePat}
                          disabled={!pat.trim() || reposLoading}
                          className="px-3 py-2 rounded-md bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium transition-colors whitespace-nowrap"
                        >
                          {reposLoading ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            "Load repos"
                          )}
                        </button>
                      </div>
                    )}
                    <p className="text-xs text-gray-400 dark:text-[#555]">
                      Needs <code className="font-mono">repo</code> scope. Saved to localStorage.
                    </p>
                  </div>
                )}

                {reposError && (
                  <p className="text-xs text-red-500 bg-red-500/10 border border-red-500/20 rounded-md px-3 py-2">
                    {reposError}
                  </p>
                )}

                {/* Repo picker */}
                {hasToken && hasRepos && (
                  <div className="space-y-3">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-[#ccc] mb-1.5">
                        Repository
                      </label>
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
                          {repos.map((r) => (
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

                {hasToken && !hasRepos && !reposLoading && !reposError && (
                  <p className="text-xs text-gray-400 dark:text-[#555]">
                    No repositories found. Check token permissions.
                  </p>
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
