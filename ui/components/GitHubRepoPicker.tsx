"use client";

import { useState, useEffect, useRef } from "react";
import type { GitHubRepo } from "@/lib/api";
import {
  Search,
  ChevronDown,
  Lock,
  Globe,
  GitBranch,
  Loader2,
  RefreshCw,
  Star,
  X,
} from "lucide-react";

interface GitHubRepoPickerProps {
  repos: GitHubRepo[];
  loading: boolean;
  selected: GitHubRepo | null;
  onSelect: (repo: GitHubRepo | null) => void;
  onRefresh?: () => void;
  className?: string;
}

export function GitHubRepoPicker({
  repos,
  loading,
  selected,
  onSelect,
  onRefresh,
  className = "",
}: GitHubRepoPickerProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const dropdownRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  // Focus search when opened
  useEffect(() => {
    if (open && searchRef.current) {
      searchRef.current.focus();
    }
  }, [open]);

  // Group repos by owner (organization)
  const grouped = new Map<string, GitHubRepo[]>();
  const filtered = repos.filter((r) => {
    if (!search) return true;
    return r.full_name.toLowerCase().includes(search.toLowerCase());
  });

  for (const repo of filtered) {
    const owner = repo.full_name.split("/")[0];
    if (!grouped.has(owner)) grouped.set(owner, []);
    grouped.get(owner)!.push(repo);
  }

  return (
    <div ref={dropdownRef} className={`relative ${className}`}>
      {/* Trigger */}
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 hover:border-gray-300 dark:hover:border-zinc-600 transition-colors group"
      >
        {selected ? (
          <div className="flex items-center gap-2.5 flex-1 min-w-0">
            <div className="w-6 h-6 rounded-md bg-gray-100 dark:bg-zinc-800 flex items-center justify-center shrink-0">
              {selected.private ? (
                <Lock className="w-3 h-3 text-amber-500" />
              ) : (
                <Globe className="w-3 h-3 text-emerald-500" />
              )}
            </div>
            <div className="flex-1 min-w-0 text-left">
              <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                {selected.name}
              </p>
              <p className="text-xs text-gray-400 dark:text-zinc-500 truncate">
                {selected.full_name}
              </p>
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              <GitBranch className="w-3 h-3 text-gray-400" />
              <span className="text-xs text-gray-400 font-mono">{selected.default_branch}</span>
            </div>
          </div>
        ) : (
          <span className="text-sm text-gray-400 dark:text-zinc-500 flex-1 text-left">
            Select a repository...
          </span>
        )}
        <div className="flex items-center gap-1 shrink-0">
          {selected && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onSelect(null);
              }}
              className="p-1 rounded hover:bg-gray-100 dark:hover:bg-zinc-800"
            >
              <X className="w-3 h-3 text-gray-400" />
            </button>
          )}
          <ChevronDown className={`w-4 h-4 text-gray-400 transition-transform ${open ? "rotate-180" : ""}`} />
        </div>
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute z-50 mt-1 w-full max-h-80 overflow-hidden rounded-xl border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 shadow-xl">
          {/* Search bar */}
          <div className="flex items-center gap-2 p-2.5 border-b border-gray-100 dark:border-zinc-800">
            <div className="relative flex-1">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
              <input
                ref={searchRef}
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search repositories..."
                className="w-full pl-8 pr-3 py-1.5 rounded-md border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-xs text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
            {onRefresh && (
              <button
                type="button"
                onClick={onRefresh}
                disabled={loading}
                className="p-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-zinc-800 text-gray-400 dark:text-zinc-500 disabled:opacity-50"
                title="Refresh repositories"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              </button>
            )}
          </div>

          {/* Results */}
          <div className="max-h-64 overflow-y-auto">
            {loading && repos.length === 0 && (
              <div className="flex items-center justify-center py-8 gap-2 text-gray-400 dark:text-zinc-500">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span className="text-xs">Loading repositories...</span>
              </div>
            )}

            {!loading && filtered.length === 0 && (
              <div className="py-6 text-center text-xs text-gray-400 dark:text-zinc-500">
                {search ? "No matching repositories" : "No repositories found"}
              </div>
            )}

            {Array.from(grouped.entries()).map(([owner, ownerRepos]) => (
              <div key={owner}>
                {/* Group header */}
                <div className="sticky top-0 px-3 py-1.5 bg-gray-50 dark:bg-zinc-800/50 border-b border-gray-100 dark:border-zinc-800">
                  <span className="text-[10px] font-semibold text-gray-500 dark:text-zinc-400 uppercase tracking-wider">
                    {owner}
                  </span>
                  <span className="ml-1.5 text-[10px] text-gray-400 dark:text-zinc-600">
                    ({ownerRepos.length})
                  </span>
                </div>

                {/* Repos */}
                {ownerRepos.map((repo) => (
                  <button
                    key={repo.id}
                    type="button"
                    onClick={() => {
                      onSelect(repo);
                      setOpen(false);
                      setSearch("");
                    }}
                    className={`w-full flex items-center gap-2.5 px-3 py-2.5 text-left hover:bg-blue-50 dark:hover:bg-blue-500/10 transition-colors ${
                      selected?.id === repo.id ? "bg-blue-50 dark:bg-blue-500/10" : ""
                    }`}
                  >
                    {/* Icon */}
                    <div className="w-5 h-5 rounded flex items-center justify-center shrink-0">
                      {repo.private ? (
                        <Lock className="w-3 h-3 text-amber-500" />
                      ) : (
                        <Globe className="w-3 h-3 text-emerald-500" />
                      )}
                    </div>

                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                        {repo.name}
                      </p>
                    </div>

                    {/* Branch + badges */}
                    <div className="flex items-center gap-2 shrink-0">
                      <span className="text-[10px] font-mono text-gray-400 dark:text-zinc-500 bg-gray-100 dark:bg-zinc-800 px-1.5 py-0.5 rounded">
                        {repo.default_branch}
                      </span>
                      {repo.private && (
                        <span className="text-[10px] text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-500/10 px-1.5 py-0.5 rounded font-medium">
                          private
                        </span>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            ))}
          </div>

          {/* Footer */}
          <div className="px-3 py-2 border-t border-gray-100 dark:border-zinc-800 bg-gray-50 dark:bg-zinc-800/50">
            <p className="text-[10px] text-gray-400 dark:text-zinc-500">
              {repos.length} {repos.length === 1 ? "repository" : "repositories"} available
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
