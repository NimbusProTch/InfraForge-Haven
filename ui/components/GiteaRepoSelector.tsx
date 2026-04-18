"use client";

import { useEffect } from "react";
import type { GiteaRepo } from "@/lib/api";
import { ChevronDown, GitBranch, Loader2, RefreshCw } from "lucide-react";

interface GiteaRepoSelectorProps {
  tenantSlug: string;
  accessToken?: string;
  repos: GiteaRepo[];
  loading: boolean;
  error: string;
  selected: GiteaRepo | null;
  branch: string;
  onBranchChange: (branch: string) => void;
  /** Called to (re)fetch the tenant's Gitea repos. */
  onLoad: () => Promise<void> | void;
  /** Called when the user picks a repo (or clears selection). */
  onSelect: (repo: GiteaRepo | null) => void;
}

/**
 * Picks a repo from the tenant's self-hosted Gitea org (tenant-{slug}).
 *
 * Backed by the existing `/api/v1/tenants/{slug}/repos` endpoint. Clone URL
 * from the selected repo is written back up into the wizard's repoUrl state
 * so the rest of the app-create flow (build, branch, port) works unchanged.
 */
export function GiteaRepoSelector({
  tenantSlug,
  accessToken,
  repos,
  loading,
  error,
  selected,
  branch,
  onBranchChange,
  onLoad,
  onSelect,
}: GiteaRepoSelectorProps) {
  // Lazy-load the first time this tab is shown
  useEffect(() => {
    if (repos.length === 0 && !loading && !error && accessToken) {
      void onLoad();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-4" data-testid="gitea-source-panel">
      <div className="flex items-center justify-between gap-3 rounded-xl border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-800/50 px-4 py-3 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-emerald-600 flex items-center justify-center">
            <GitBranch className="w-5 h-5 text-white" />
          </div>
          <div>
            <p className="text-sm font-medium text-gray-900 dark:text-zinc-100">
              Self-hosted Gitea
            </p>
            <p className="text-xs text-gray-400 dark:text-zinc-500 font-mono">
              tenant-{tenantSlug}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => void onLoad()}
          disabled={loading}
          title="Refresh repositories"
          className="p-2 rounded-lg text-gray-400 hover:text-gray-600 dark:text-zinc-500 dark:hover:text-zinc-300 hover:bg-gray-100 dark:hover:bg-zinc-700 transition-colors disabled:opacity-50"
          data-testid="gitea-refresh"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {error && (
        <p className="text-xs text-red-500 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      {loading && repos.length === 0 && (
        <div
          className="flex items-center gap-2 text-sm text-gray-400 dark:text-zinc-500 py-4 justify-center"
          data-testid="gitea-loading"
        >
          <Loader2 className="w-4 h-4 animate-spin" />
          Loading Gitea repositories...
        </div>
      )}

      {!loading && repos.length === 0 && !error && (
        <div className="text-xs text-gray-500 dark:text-zinc-400 bg-gray-50 dark:bg-zinc-900/50 border border-gray-200 dark:border-zinc-700 rounded-lg px-3 py-3">
          No repositories yet in <code className="font-mono">tenant-{tenantSlug}</code>.
          Create one through the Gitea UI, or push an existing project to the
          tenant&apos;s clone URL, then hit refresh.
        </div>
      )}

      {repos.length > 0 && (
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1.5">
            Repository
          </label>
          <div className="relative">
            <select
              data-testid="gitea-repo-select"
              value={selected?.name ?? ""}
              onChange={(e) => {
                const repo = repos.find((r) => r.name === e.target.value) ?? null;
                onSelect(repo);
              }}
              className="w-full px-4 py-2.5 pr-8 text-sm rounded-lg appearance-none bg-white dark:bg-[#0f0f0f] border border-gray-200 dark:border-[#2e2e2e] text-gray-900 dark:text-white font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/40"
            >
              <option value="">— select a repository —</option>
              {repos.map((r) => (
                <option key={r.id} value={r.name}>
                  {r.name}
                  {r.empty ? " (empty)" : ""}
                </option>
              ))}
            </select>
            <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
          </div>
        </div>
      )}

      {selected && (
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1.5">
            Branch
          </label>
          <input
            type="text"
            value={branch}
            onChange={(e) => onBranchChange(e.target.value)}
            placeholder={selected.default_branch || "main"}
            className="w-full px-4 py-2.5 text-sm rounded-lg bg-white dark:bg-[#0f0f0f] border border-gray-200 dark:border-[#2e2e2e] text-gray-900 dark:text-white font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/40"
            data-testid="gitea-branch-input"
          />
        </div>
      )}
    </div>
  );
}
