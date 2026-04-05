"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { api, type RepoTreeItem } from "@/lib/api";
import {
  File,
  Folder,
  ChevronDown,
  Loader2,
  Search,
  X,
} from "lucide-react";

interface GitHubFileBrowserProps {
  owner: string;
  repo: string;
  branch: string;
  token: string;
  /** "file" to select files, "directory" to select directories */
  mode?: "file" | "directory";
  /** Glob-like filter pattern (e.g., "Dockerfile" matches any path containing it) */
  filter?: string;
  placeholder?: string;
  value?: string;
  onSelect: (path: string) => void;
  className?: string;
}

export function GitHubFileBrowser({
  owner,
  repo,
  branch,
  token,
  mode = "file",
  filter,
  placeholder = "Select a file...",
  value,
  onSelect,
  className = "",
}: GitHubFileBrowserProps) {
  const [open, setOpen] = useState(false);
  const [tree, setTree] = useState<RepoTreeItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const dropdownRef = useRef<HTMLDivElement>(null);

  const loadTree = useCallback(async () => {
    if (!owner || !repo || !branch || !token) return;
    setLoading(true);
    setError("");
    try {
      const data = await api.github.tree(owner, repo, branch, token);
      setTree(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load file tree");
    } finally {
      setLoading(false);
    }
  }, [owner, repo, branch, token]);

  // Load tree lazily when dropdown opens for the first time
  useEffect(() => {
    if (open && tree.length === 0 && !loading && !error) {
      loadTree();
    }
  }, [open, tree.length, loading, error, loadTree]);

  // Close dropdown on outside click
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

  // Filter items based on mode and search
  const filteredItems = tree.filter((item) => {
    // Filter by type
    if (mode === "directory" && item.type !== "tree") return false;
    if (mode === "file" && item.type !== "blob") return false;

    // Filter by pattern
    if (filter) {
      const lowerPath = item.path.toLowerCase();
      const lowerFilter = filter.toLowerCase();
      if (!lowerPath.includes(lowerFilter)) return false;
    }

    // Filter by search
    if (search) {
      const lowerPath = item.path.toLowerCase();
      const lowerSearch = search.toLowerCase();
      if (!lowerPath.includes(lowerSearch)) return false;
    }

    return true;
  });

  const displayValue = value || "";

  return (
    <div ref={dropdownRef} className={`relative ${className}`}>
      {/* Trigger */}
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between gap-2 px-3 py-2 rounded-lg border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 text-sm hover:border-gray-300 dark:hover:border-zinc-600 transition-colors"
      >
        <span className={displayValue ? "text-gray-900 dark:text-white font-mono text-xs" : "text-gray-400 dark:text-zinc-500"}>
          {displayValue || placeholder}
        </span>
        <div className="flex items-center gap-1.5 shrink-0">
          {displayValue && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onSelect("");
                setOpen(false);
              }}
              className="p-0.5 rounded hover:bg-gray-100 dark:hover:bg-zinc-800"
            >
              <X className="w-3 h-3 text-gray-400" />
            </button>
          )}
          <ChevronDown className={`w-3.5 h-3.5 text-gray-400 transition-transform ${open ? "rotate-180" : ""}`} />
        </div>
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute z-50 mt-1 w-full max-h-72 overflow-hidden rounded-lg border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 shadow-xl">
          {/* Search */}
          <div className="p-2 border-b border-gray-100 dark:border-zinc-800">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={`Search ${mode === "directory" ? "directories" : "files"}...`}
                className="w-full pl-8 pr-3 py-1.5 rounded-md border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-xs text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                autoFocus
              />
            </div>
          </div>

          {/* Content */}
          <div className="max-h-56 overflow-y-auto">
            {loading && (
              <div className="flex items-center justify-center py-8 gap-2 text-gray-400 dark:text-zinc-500">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span className="text-xs">Loading repository files...</span>
              </div>
            )}

            {error && (
              <div className="p-4 text-center">
                <p className="text-xs text-red-500">{error}</p>
                <button
                  type="button"
                  onClick={loadTree}
                  className="mt-2 text-xs text-blue-500 hover:text-blue-600"
                >
                  Retry
                </button>
              </div>
            )}

            {!loading && !error && filteredItems.length === 0 && (
              <div className="py-6 text-center text-xs text-gray-400 dark:text-zinc-500">
                {tree.length === 0
                  ? "No files found in repository"
                  : `No matching ${mode === "directory" ? "directories" : "files"}`}
              </div>
            )}

            {filteredItems.map((item) => (
              <button
                key={item.path}
                type="button"
                onClick={() => {
                  onSelect(item.path);
                  setOpen(false);
                  setSearch("");
                }}
                className={`w-full flex items-center gap-2.5 px-3 py-2 text-left text-xs hover:bg-blue-50 dark:hover:bg-blue-500/10 transition-colors ${
                  value === item.path ? "bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400" : "text-gray-700 dark:text-zinc-300"
                }`}
              >
                {item.type === "tree" ? (
                  <Folder className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                ) : (
                  <File className="w-3.5 h-3.5 text-gray-400 dark:text-zinc-500 shrink-0" />
                )}
                <span className="font-mono truncate">{item.path}</span>
                {item.size != null && item.type === "blob" && (
                  <span className="ml-auto text-gray-400 dark:text-zinc-600 shrink-0">
                    {item.size > 1024 ? `${(item.size / 1024).toFixed(1)}KB` : `${item.size}B`}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
