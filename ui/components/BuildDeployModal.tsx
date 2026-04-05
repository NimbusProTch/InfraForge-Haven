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
  onConfirm: (options: { branch?: string }) => void;
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

  if (!open) return null;

  const repoShort = repoUrl.replace("https://github.com/", "");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl shadow-2xl w-full max-w-lg mx-4" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
              <Hammer className="w-4 h-4 text-amber-400" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-zinc-100">Build &amp; Deploy</h3>
              <p className="text-xs text-zinc-500">{appName}</p>
            </div>
          </div>
          <button onClick={onClose} className="text-zinc-600 hover:text-zinc-300 transition-colors p-1 rounded-lg hover:bg-zinc-800">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-4">
          {/* Repository info */}
          <div className="flex items-center gap-3 bg-zinc-800/50 rounded-lg px-3 py-2.5">
            <FileCode className="w-4 h-4 text-zinc-500 shrink-0" />
            <div className="min-w-0">
              <p className="text-xs text-zinc-400 font-mono truncate">{repoShort}</p>
              {useDockerfile && dockerfilePath && (
                <p className="text-[10px] text-zinc-600 mt-0.5">Dockerfile: {dockerfilePath}</p>
              )}
              {!useDockerfile && (
                <p className="text-[10px] text-zinc-600 mt-0.5">Auto-detect via Nixpacks</p>
              )}
            </div>
          </div>

          {/* Branch */}
          <div>
            <label className="flex items-center gap-1.5 text-xs text-zinc-500 mb-1.5">
              <GitBranch className="w-3 h-3" />
              Branch
            </label>
            <input
              type="text"
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-800 text-sm text-zinc-200 font-mono focus:outline-none focus:ring-1 focus:ring-amber-500/50 focus:border-amber-500/50"
            />
          </div>

          {/* Advanced toggle */}
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            <ChevronDown className={`w-3 h-3 transition-transform ${showAdvanced ? "rotate-180" : ""}`} />
            Advanced options
          </button>

          {showAdvanced && (
            <div className="space-y-3 pl-4 border-l-2 border-zinc-800">
              <p className="text-[11px] text-zinc-600">
                Environment variables and Dockerfile settings can be configured in the Settings tab before building.
              </p>
            </div>
          )}

          {/* Pipeline steps preview */}
          <div className="bg-zinc-800/30 rounded-lg p-3 border border-zinc-800/50">
            <p className="text-xs text-zinc-500 mb-2">Build pipeline:</p>
            <div className="flex items-center gap-2">
              {["Clone", "Detect", "Build", "Push", "Deploy"].map((step, i) => (
                <div key={step} className="flex items-center gap-2">
                  <span className="text-[10px] text-zinc-400 bg-zinc-800 px-2 py-0.5 rounded font-medium">{step}</span>
                  {i < 4 && <span className="text-zinc-700">→</span>}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 py-4 border-t border-zinc-800">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg border border-zinc-700 text-zinc-400 hover:text-zinc-200 text-xs font-medium transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => onConfirm({ branch })}
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
  onConfirm: () => void;
  loading: boolean;
  appName: string;
  imageTag: string | null;
  replicas?: number;
}

export function DeployModal({
  open,
  onClose,
  onConfirm,
  loading,
  appName,
  imageTag,
  replicas = 1,
}: DeployModalProps) {
  if (!open) return null;

  const imageShort = imageTag?.split(":").pop() ?? "latest";
  const imageRepo = imageTag?.split(":")[0]?.split("/").pop() ?? "";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl shadow-2xl w-full max-w-lg mx-4" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
              <Rocket className="w-4 h-4 text-emerald-400" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-zinc-100">Deploy Application</h3>
              <p className="text-xs text-zinc-500">{appName}</p>
            </div>
          </div>
          <button onClick={onClose} className="text-zinc-600 hover:text-zinc-300 transition-colors p-1 rounded-lg hover:bg-zinc-800">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-4">
          {/* Image info */}
          <div>
            <p className="text-xs text-zinc-500 mb-1.5">Container Image</p>
            <div className="bg-zinc-800 rounded-lg px-3 py-2.5 border border-zinc-700">
              <p className="text-sm text-zinc-200 font-mono">{imageRepo}:<span className="text-emerald-400">{imageShort}</span></p>
            </div>
          </div>

          {/* Deployment info */}
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-zinc-800/50 rounded-lg px-3 py-2.5">
              <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Replicas</p>
              <p className="text-sm text-zinc-200 font-medium">{replicas}</p>
            </div>
            <div className="bg-zinc-800/50 rounded-lg px-3 py-2.5">
              <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Strategy</p>
              <p className="text-sm text-zinc-200 font-medium">Rolling Update</p>
            </div>
          </div>

          {/* Warning */}
          <div className="bg-amber-500/5 border border-amber-500/10 rounded-lg p-3">
            <p className="text-xs text-amber-300/80">
              This will replace the running pods with the new image version.
              Existing connections will be gracefully terminated.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 py-4 border-t border-zinc-800">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg border border-zinc-700 text-zinc-400 hover:text-zinc-200 text-xs font-medium transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
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
