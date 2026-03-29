"use client";

import { useEffect, useState, useCallback } from "react";
import { api, type Environment } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { Badge } from "@/components/ui/badge";
import {
  Plus,
  Loader2,
  Globe,
  GitBranch,
  Trash2,
  ExternalLink,
  Copy,
  Check,
  Layers,
  X,
  GitPullRequest,
} from "lucide-react";

const ENV_TYPE_CONFIG = {
  production: {
    color: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    dot: "bg-emerald-500",
    label: "Production",
  },
  staging: {
    color: "bg-amber-500/10 text-amber-400 border-amber-500/20",
    dot: "bg-amber-500",
    label: "Staging",
  },
  preview: {
    color: "bg-blue-500/10 text-blue-400 border-blue-500/20",
    dot: "bg-blue-500",
    label: "Preview",
  },
};

const STATUS_VARIANT: Record<string, "success" | "warning" | "destructive" | "secondary"> = {
  running: "success",
  building: "warning",
  pending: "secondary",
  failed: "destructive",
  deleting: "secondary",
};

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      className="text-zinc-600 hover:text-zinc-300 transition-colors"
    >
      {copied ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
    </button>
  );
}

interface EnvironmentsTabProps {
  tenantSlug: string;
  appSlug: string;
  accessToken?: string;
}

export default function EnvironmentsTab({ tenantSlug, appSlug, accessToken }: EnvironmentsTabProps) {
  const { error: toastError, success: toastSuccess } = useToast();
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  // Create form state
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState<"staging" | "preview">("staging");
  const [newBranch, setNewBranch] = useState("develop");

  const loadEnvs = useCallback(async () => {
    try {
      const envs = await api.environments.list(tenantSlug, appSlug, accessToken);
      setEnvironments(envs);
    } catch {
      // Silent — environments may not be available
    } finally {
      setLoading(false);
    }
  }, [tenantSlug, appSlug, accessToken]);

  useEffect(() => {
    loadEnvs();
  }, [loadEnvs]);

  async function createEnvironment() {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const env = await api.environments.create(tenantSlug, appSlug, {
        name: newName.toLowerCase().replace(/[^a-z0-9-]/g, "-"),
        env_type: newType,
        branch: newBranch,
      }, accessToken);
      setEnvironments((prev) => [...prev, env]);
      toastSuccess(`Environment "${env.name}" created`);
      setShowCreate(false);
      setNewName("");
      setNewBranch("develop");
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Failed to create environment");
    } finally {
      setCreating(false);
    }
  }

  async function deleteEnvironment(name: string) {
    setDeleting(name);
    try {
      await api.environments.delete(tenantSlug, appSlug, name, accessToken);
      setEnvironments((prev) => prev.filter((e) => e.name !== name));
      toastSuccess(`Environment "${name}" deleted`);
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Failed to delete environment");
    } finally {
      setDeleting(null);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-5 h-5 animate-spin text-zinc-600" />
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <p className="text-sm text-zinc-500">
            Deploy to staging, preview, or custom environments
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium transition-colors"
        >
          <Plus className="w-3 h-3" />
          New Environment
        </button>
      </div>

      {/* Create modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl w-full max-w-md mx-4 shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
              <div className="flex items-center gap-2">
                <Layers className="w-4 h-4 text-blue-500" />
                <h2 className="text-sm font-semibold text-zinc-100">Create Environment</h2>
              </div>
              <button onClick={() => setShowCreate(false)} className="text-zinc-600 hover:text-zinc-300 transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-5 space-y-4">
              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1.5">Name</label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="staging-v2"
                  className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-800 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-blue-600 focus:ring-1 focus:ring-blue-600/30 font-mono"
                />
                <p className="text-xs text-zinc-600 mt-1">Lowercase letters, numbers, and hyphens only.</p>
              </div>

              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1.5">Type</label>
                <div className="grid grid-cols-2 gap-2">
                  {(["staging", "preview"] as const).map((type) => {
                    const cfg = ENV_TYPE_CONFIG[type];
                    return (
                      <button
                        key={type}
                        onClick={() => setNewType(type)}
                        className={`px-3 py-2.5 rounded-lg border text-sm font-medium transition-colors ${
                          newType === type
                            ? cfg.color + " border-current"
                            : "bg-zinc-800/50 border-zinc-800 text-zinc-500 hover:border-zinc-700"
                        }`}
                      >
                        {cfg.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1.5">Branch</label>
                <input
                  type="text"
                  value={newBranch}
                  onChange={(e) => setNewBranch(e.target.value)}
                  placeholder="develop"
                  className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-800 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-blue-600 focus:ring-1 focus:ring-blue-600/30 font-mono"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  onClick={() => setShowCreate(false)}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={createEnvironment}
                  disabled={!newName.trim() || creating}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {creating && <Loader2 className="w-3 h-3 animate-spin" />}
                  Create
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Environment list */}
      {environments.length === 0 ? (
        <div className="text-center py-16 border border-dashed border-zinc-800 rounded-xl">
          <Layers className="w-8 h-8 mx-auto mb-2 text-zinc-700" />
          <p className="text-sm text-zinc-500">No environments configured.</p>
          <p className="text-xs text-zinc-600 mt-1">
            Create a staging or preview environment, or push a PR to auto-create a preview.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {environments.map((env) => {
            const cfg = ENV_TYPE_CONFIG[env.env_type] ?? ENV_TYPE_CONFIG.staging;
            const isProduction = env.env_type === "production";

            return (
              <div
                key={env.id}
                className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-4 hover:border-zinc-700 transition-colors"
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`w-2 h-2 rounded-full ${cfg.dot}`} />
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-zinc-200">{env.name}</span>
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${cfg.color}`}>
                          {cfg.label}
                        </span>
                        <Badge variant={STATUS_VARIANT[env.status] ?? "secondary"}>
                          {env.status}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-3 mt-1.5 text-xs text-zinc-600">
                        <span className="flex items-center gap-1">
                          <GitBranch className="w-3 h-3" />
                          {env.branch}
                        </span>
                        {env.pr_number && (
                          <span className="flex items-center gap-1 text-blue-500">
                            <GitPullRequest className="w-3 h-3" />
                            PR #{env.pr_number}
                          </span>
                        )}
                        {env.replicas && (
                          <span>{env.replicas} replica{env.replicas !== 1 ? "s" : ""}</span>
                        )}
                        {env.last_image_tag && (
                          <span className="font-mono">{env.last_image_tag.slice(0, 8)}</span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {env.domain && (
                      <a
                        href={`https://${env.domain}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-xs font-medium text-zinc-300 hover:text-zinc-100 transition-colors"
                      >
                        <Globe className="w-3 h-3" />
                        Open
                        <ExternalLink className="w-2.5 h-2.5" />
                      </a>
                    )}
                    {!isProduction && (
                      <button
                        onClick={() => deleteEnvironment(env.name)}
                        disabled={deleting === env.name}
                        className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium text-zinc-600 hover:text-red-400 hover:bg-red-950/30 transition-colors disabled:opacity-50"
                      >
                        {deleting === env.name ? (
                          <Loader2 className="w-3 h-3 animate-spin" />
                        ) : (
                          <Trash2 className="w-3 h-3" />
                        )}
                      </button>
                    )}
                  </div>
                </div>

                {/* Domain row */}
                {env.domain && (
                  <div className="mt-3 flex items-center gap-1 bg-zinc-800/50 rounded-lg px-3 py-2">
                    <Globe className="w-3 h-3 text-zinc-600 shrink-0" />
                    <span className="text-xs font-mono text-zinc-400 truncate flex-1">
                      {env.domain}
                    </span>
                    <CopyButton text={env.domain} />
                  </div>
                )}

                {/* Env vars count */}
                {env.env_vars && Object.keys(env.env_vars).length > 0 && (
                  <p className="mt-2 text-xs text-zinc-600">
                    {Object.keys(env.env_vars).length} environment variable{Object.keys(env.env_vars).length !== 1 ? "s" : ""} overridden
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
