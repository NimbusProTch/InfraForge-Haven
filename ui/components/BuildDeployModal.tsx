"use client";

import { useState } from "react";
import {
  Hammer,
  Rocket,
  Loader2,
  GitBranch,
  X,
  FileCode,
  ChevronDown,
  Plus,
  Trash2,
} from "lucide-react";

// ---- Build Modal ----

interface BuildModalProps {
  open: boolean;
  onClose: () => void;
  onConfirm: (options: { branch?: string; build_env_vars?: Record<string, string> }) => void;
  loading: boolean;
  appName: string;
  currentBranch: string;
  repoUrl: string;
  useDockerfile?: boolean;
  dockerfilePath?: string | null;
}

export function BuildModal({
  open,
  onClose,
  onConfirm,
  loading,
  appName,
  currentBranch,
  repoUrl,
  useDockerfile = false,
  dockerfilePath,
}: BuildModalProps) {
  const [branch, setBranch] = useState(currentBranch);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [envVars, setEnvVars] = useState<Array<{ key: string; value: string }>>([]);

  if (!open) return null;

  const repoShort = repoUrl.replace("https://github.com/", "");

  const addEnvVar = () => setEnvVars([...envVars, { key: "", value: "" }]);
  const removeEnvVar = (i: number) => setEnvVars(envVars.filter((_, idx) => idx !== i));
  const updateEnvVar = (i: number, field: "key" | "value", val: string) => {
    const updated = [...envVars];
    updated[i][field] = val;
    setEnvVars(updated);
  };

  const handleConfirm = () => {
    const buildEnvVars: Record<string, string> = {};
    envVars.forEach(({ key, value }) => {
      if (key.trim()) buildEnvVars[key.trim()] = value;
    });
    onConfirm({
      branch: branch !== currentBranch ? branch : undefined,
      build_env_vars: Object.keys(buildEnvVars).length > 0 ? buildEnvVars : undefined,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-800 rounded-2xl shadow-2xl w-full max-w-lg mx-4" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-zinc-800">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
              <Hammer className="w-4 h-4 text-amber-400" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-gray-900 dark:text-zinc-100">Build &amp; Deploy</h3>
              <p className="text-xs text-gray-500 dark:text-zinc-500">{appName}</p>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 dark:text-zinc-600 hover:text-gray-700 dark:hover:text-zinc-300 transition-colors p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-zinc-800">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-4">
          {/* Repository info */}
          <div className="flex items-center gap-3 bg-gray-50 dark:bg-zinc-800/50 rounded-lg px-3 py-2.5">
            <FileCode className="w-4 h-4 text-gray-500 dark:text-zinc-500 shrink-0" />
            <div className="min-w-0">
              <p className="text-xs text-gray-500 dark:text-zinc-400 font-mono truncate">{repoShort}</p>
              {useDockerfile && dockerfilePath && (
                <p className="text-[10px] text-gray-400 dark:text-zinc-600 mt-0.5">Dockerfile: {dockerfilePath}</p>
              )}
              {!useDockerfile && (
                <p className="text-[10px] text-gray-400 dark:text-zinc-600 mt-0.5">Auto-detect via Nixpacks</p>
              )}
            </div>
          </div>

          {/* Branch */}
          <div>
            <label className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-zinc-500 mb-1.5">
              <GitBranch className="w-3 h-3" />
              Branch
            </label>
            <input
              type="text"
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-zinc-700 bg-gray-100 dark:bg-zinc-800 text-sm text-gray-800 dark:text-zinc-200 font-mono focus:outline-none focus:ring-1 focus:ring-amber-500/50 focus:border-amber-500/50"
            />
          </div>

          {/* Build Environment (collapsible) */}
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-zinc-500 hover:text-gray-700 dark:hover:text-zinc-300 transition-colors"
          >
            <ChevronDown className={`w-3 h-3 transition-transform ${showAdvanced ? "rotate-180" : ""}`} />
            Build Environment (optional)
          </button>

          {showAdvanced && (
            <div className="space-y-2 pl-4 border-l-2 border-gray-200 dark:border-zinc-800">
              <p className="text-[11px] text-gray-400 dark:text-zinc-600 mb-2">
                Override environment variables for this build only.
              </p>
              {envVars.map((ev, i) => (
                <div key={i} className="flex items-center gap-2">
                  <input
                    type="text"
                    placeholder="KEY"
                    value={ev.key}
                    onChange={(e) => updateEnvVar(i, "key", e.target.value)}
                    className="flex-1 px-2 py-1.5 rounded border border-gray-300 dark:border-zinc-700 bg-gray-100 dark:bg-zinc-800 text-xs text-gray-800 dark:text-zinc-200 font-mono focus:outline-none focus:ring-1 focus:ring-amber-500/50"
                  />
                  <span className="text-gray-400 dark:text-zinc-600 text-xs">=</span>
                  <input
                    type="text"
                    placeholder="value"
                    value={ev.value}
                    onChange={(e) => updateEnvVar(i, "value", e.target.value)}
                    className="flex-1 px-2 py-1.5 rounded border border-gray-300 dark:border-zinc-700 bg-gray-100 dark:bg-zinc-800 text-xs text-gray-800 dark:text-zinc-200 font-mono focus:outline-none focus:ring-1 focus:ring-amber-500/50"
                  />
                  <button onClick={() => removeEnvVar(i)} className="text-gray-400 dark:text-zinc-600 hover:text-red-400 transition-colors">
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              ))}
              <button
                type="button"
                onClick={addEnvVar}
                className="inline-flex items-center gap-1 text-xs text-gray-500 dark:text-zinc-500 hover:text-gray-700 dark:hover:text-zinc-300 transition-colors"
              >
                <Plus className="w-3 h-3" />
                Add variable
              </button>
            </div>
          )}

          {/* Pipeline steps preview */}
          <div className="bg-gray-50 dark:bg-zinc-800/30 rounded-lg p-3 border border-gray-200 dark:border-zinc-800/50">
            <p className="text-xs text-gray-500 dark:text-zinc-500 mb-2">Build pipeline:</p>
            <div className="flex items-center gap-2">
              {["Clone", "Detect", "Build", "Push", "Deploy"].map((step, i) => (
                <div key={step} className="flex items-center gap-2">
                  <span className="text-[10px] text-gray-500 dark:text-zinc-400 bg-gray-100 dark:bg-zinc-800 px-2 py-0.5 rounded font-medium">{step}</span>
                  {i < 4 && <span className="text-gray-400 dark:text-zinc-700">→</span>}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 py-4 border-t border-gray-200 dark:border-zinc-800">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg border border-gray-300 dark:border-zinc-700 text-gray-500 dark:text-zinc-400 hover:text-gray-900 dark:hover:text-zinc-200 text-xs font-medium transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-5 py-2 rounded-lg bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white text-xs font-medium transition-colors"
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Hammer className="w-3.5 h-3.5" />}
            Start Build
          </button>
        </div>
      </div>
    </div>
  );
}

// ---- Deploy Modal ----

interface DeployModalProps {
  open: boolean;
  onClose: () => void;
  onConfirm: (options: { replicas?: number; resource_cpu_limit?: string; resource_memory_limit?: string }) => void;
  loading: boolean;
  appName: string;
  imageTag: string | null;
  replicas?: number;
  cpuLimit?: string;
  memoryLimit?: string;
}

export function DeployModal({
  open,
  onClose,
  onConfirm,
  loading,
  appName,
  imageTag,
  replicas = 1,
  cpuLimit = "500m",
  memoryLimit = "512Mi",
}: DeployModalProps) {
  const [selectedReplicas, setSelectedReplicas] = useState(replicas);
  const [cpu, setCpu] = useState(cpuLimit);
  const [memory, setMemory] = useState(memoryLimit);

  if (!open) return null;

  const imageShort = imageTag?.split(":").pop() ?? "latest";
  const imageRepo = imageTag?.split(":")[0]?.split("/").pop() ?? "";

  const handleConfirm = () => {
    onConfirm({
      replicas: selectedReplicas !== replicas ? selectedReplicas : undefined,
      resource_cpu_limit: cpu !== cpuLimit ? cpu : undefined,
      resource_memory_limit: memory !== memoryLimit ? memory : undefined,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-800 rounded-2xl shadow-2xl w-full max-w-lg mx-4" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-zinc-800">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
              <Rocket className="w-4 h-4 text-emerald-400" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-gray-900 dark:text-zinc-100">Deploy Application</h3>
              <p className="text-xs text-gray-500 dark:text-zinc-500">{appName}</p>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 dark:text-zinc-600 hover:text-gray-700 dark:hover:text-zinc-300 transition-colors p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-zinc-800">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-4">
          {/* Image info */}
          <div>
            <p className="text-xs text-gray-500 dark:text-zinc-500 mb-1.5">Container Image</p>
            <div className="bg-gray-100 dark:bg-zinc-800 rounded-lg px-3 py-2.5 border border-gray-300 dark:border-zinc-700">
              <p className="text-sm text-gray-800 dark:text-zinc-200 font-mono">{imageRepo}:<span className="text-emerald-400">{imageShort}</span></p>
            </div>
          </div>

          {/* Replicas */}
          <div>
            <p className="text-[10px] text-gray-500 dark:text-zinc-500 uppercase tracking-wider mb-2">Replicas</p>
            <div className="flex items-center gap-2">
              {[1, 2, 3, 5].map((n) => (
                <button
                  key={n}
                  onClick={() => setSelectedReplicas(n)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    selectedReplicas === n
                      ? "bg-emerald-600 text-white"
                      : "bg-gray-100 dark:bg-zinc-800 text-gray-500 dark:text-zinc-400 hover:bg-gray-200 dark:hover:bg-zinc-700 hover:text-gray-900 dark:hover:text-zinc-200 border border-gray-300 dark:border-zinc-700"
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>

          {/* Resource Limits */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="text-[10px] text-gray-500 dark:text-zinc-500 uppercase tracking-wider mb-1.5">CPU Limit</p>
              <input
                type="text"
                value={cpu}
                onChange={(e) => setCpu(e.target.value)}
                placeholder="500m"
                className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-zinc-700 bg-gray-100 dark:bg-zinc-800 text-sm text-gray-800 dark:text-zinc-200 font-mono focus:outline-none focus:ring-1 focus:ring-emerald-500/50"
              />
            </div>
            <div>
              <p className="text-[10px] text-gray-500 dark:text-zinc-500 uppercase tracking-wider mb-1.5">Memory Limit</p>
              <input
                type="text"
                value={memory}
                onChange={(e) => setMemory(e.target.value)}
                placeholder="512Mi"
                className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-zinc-700 bg-gray-100 dark:bg-zinc-800 text-sm text-gray-800 dark:text-zinc-200 font-mono focus:outline-none focus:ring-1 focus:ring-emerald-500/50"
              />
            </div>
          </div>

          {/* Strategy info */}
          <div className="bg-gray-50 dark:bg-zinc-800/50 rounded-lg px-3 py-2.5">
            <p className="text-[10px] text-gray-500 dark:text-zinc-500 uppercase tracking-wider mb-1">Strategy</p>
            <p className="text-sm text-gray-800 dark:text-zinc-200 font-medium">Rolling Update</p>
          </div>

          {/* Warning */}
          <div className="bg-amber-500/5 border border-amber-500/10 rounded-lg p-3">
            <p className="text-xs text-amber-300/80">
              Pods will be restarted. Existing connections will be gracefully terminated.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 py-4 border-t border-gray-200 dark:border-zinc-800">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg border border-gray-300 dark:border-zinc-700 text-gray-500 dark:text-zinc-400 hover:text-gray-900 dark:hover:text-zinc-200 text-xs font-medium transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white text-xs font-medium transition-colors"
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Rocket className="w-3.5 h-3.5" />}
            Deploy Now
          </button>
        </div>
      </div>
    </div>
  );
}
