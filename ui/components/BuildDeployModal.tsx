"use client";

import { useState } from "react";
import { Hammer, Rocket, Loader2, GitBranch, X } from "lucide-react";

interface BuildModalProps {
  open: boolean;
  onClose: () => void;
  onConfirm: (options: { branch?: string }) => void;
  loading: boolean;
  appName: string;
  currentBranch: string;
  repoUrl: string;
}

export function BuildModal({
  open,
  onClose,
  onConfirm,
  loading,
  appName,
  currentBranch,
  repoUrl,
}: BuildModalProps) {
  const [branch, setBranch] = useState(currentBranch);

  if (!open) return null;

  const repoShort = repoUrl.replace("https://github.com/", "");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl shadow-2xl w-full max-w-md mx-4">
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
              <Hammer className="w-4 h-4 text-amber-400" />
            </div>
            <h3 className="text-sm font-semibold text-zinc-100">Build Application</h3>
          </div>
          <button onClick={onClose} className="text-zinc-600 hover:text-zinc-300 transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-5 py-4 space-y-4">
          <div>
            <p className="text-xs text-zinc-500 mb-1">Application</p>
            <p className="text-sm text-zinc-200 font-medium">{appName}</p>
          </div>

          <div>
            <p className="text-xs text-zinc-500 mb-1">Repository</p>
            <p className="text-xs text-zinc-400 font-mono">{repoShort}</p>
          </div>

          <div>
            <label className="block text-xs text-zinc-500 mb-1.5">
              <GitBranch className="w-3 h-3 inline mr-1" />
              Branch
            </label>
            <input
              type="text"
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-800 text-sm text-zinc-200 font-mono focus:outline-none focus:ring-1 focus:ring-amber-500/50 focus:border-amber-500/50"
            />
          </div>

          <div className="bg-zinc-800/50 rounded-lg p-3">
            <p className="text-xs text-zinc-500">This will:</p>
            <ul className="text-xs text-zinc-400 mt-1.5 space-y-1">
              <li>1. Clone the repository from <span className="font-mono text-zinc-300">{branch}</span></li>
              <li>2. Auto-detect language and framework (Nixpacks)</li>
              <li>3. Build Docker image and push to Harbor</li>
              <li>4. Deploy to the cluster via ArgoCD</li>
            </ul>
          </div>
        </div>

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
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white text-xs font-medium transition-colors"
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Hammer className="w-3.5 h-3.5" />}
            Start Build
          </button>
        </div>
      </div>
    </div>
  );
}

interface DeployModalProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  loading: boolean;
  appName: string;
  imageTag: string | null;
}

export function DeployModal({
  open,
  onClose,
  onConfirm,
  loading,
  appName,
  imageTag,
}: DeployModalProps) {
  if (!open) return null;

  const imageShort = imageTag?.split(":").pop() ?? "latest";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl shadow-2xl w-full max-w-md mx-4">
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
              <Rocket className="w-4 h-4 text-emerald-400" />
            </div>
            <h3 className="text-sm font-semibold text-zinc-100">Deploy Application</h3>
          </div>
          <button onClick={onClose} className="text-zinc-600 hover:text-zinc-300 transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-5 py-4 space-y-4">
          <div>
            <p className="text-xs text-zinc-500 mb-1">Application</p>
            <p className="text-sm text-zinc-200 font-medium">{appName}</p>
          </div>

          <div>
            <p className="text-xs text-zinc-500 mb-1">Image</p>
            <p className="text-sm text-zinc-300 font-mono bg-zinc-800 rounded-lg px-3 py-2">{imageShort}</p>
          </div>

          <div className="bg-emerald-500/5 border border-emerald-500/10 rounded-lg p-3">
            <p className="text-xs text-zinc-400">
              This will deploy the built image to the cluster. The existing pods will be replaced with the new version using a rolling update strategy.
            </p>
          </div>
        </div>

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
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white text-xs font-medium transition-colors"
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Rocket className="w-3.5 h-3.5" />}
            Deploy Now
          </button>
        </div>
      </div>
    </div>
  );
}
