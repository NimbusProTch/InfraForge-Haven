"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Layers, Loader2, Zap, Shield, Cpu, TrendingUp } from "lucide-react";

const REPLICA_PRESETS = [1, 2, 3, 5];

const RESOURCE_TIERS = [
  { id: "starter", label: "Starter", cpu: "100m / 200m", mem: "128Mi / 256Mi", cpuReq: "100m", cpuLim: "200m", memReq: "128Mi", memLim: "256Mi", icon: Zap },
  { id: "standard", label: "Standard", cpu: "500m / 1000m", mem: "512Mi / 1Gi", cpuReq: "500m", cpuLim: "1000m", memReq: "512Mi", memLim: "1Gi", icon: Shield },
  { id: "performance", label: "Performance", cpu: "1000m / 2000m", mem: "1Gi / 2Gi", cpuReq: "1000m", cpuLim: "2000m", memReq: "1Gi", memLim: "2Gi", icon: Cpu },
] as const;

interface ScaleModalProps {
  open: boolean;
  onClose: () => void;
  tenantSlug: string;
  appSlug: string;
  currentReplicas: number;
  currentCpuRequest: string;
  currentCpuLimit: string;
  currentMemoryRequest: string;
  currentMemoryLimit: string;
  minReplicas: number;
  maxReplicas: number;
  cpuThreshold: number;
  accessToken?: string;
  onSuccess: () => void;
}

export function ScaleModal({
  open,
  onClose,
  tenantSlug,
  appSlug,
  currentReplicas,
  currentCpuRequest,
  currentCpuLimit,
  currentMemoryRequest,
  currentMemoryLimit,
  minReplicas,
  maxReplicas,
  cpuThreshold,
  accessToken,
  onSuccess,
}: ScaleModalProps) {
  const [replicas, setReplicas] = useState(currentReplicas);
  const [hpaEnabled, setHpaEnabled] = useState(minReplicas !== maxReplicas);
  const [minR, setMinR] = useState(minReplicas);
  const [maxR, setMaxR] = useState(maxReplicas);
  const [cpuTarget, setCpuTarget] = useState(cpuThreshold);
  const [selectedTier, setSelectedTier] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Reset state when modal opens (prevents stale values after scaling)
  useEffect(() => {
    if (open) {
      setReplicas(currentReplicas);
      setHpaEnabled(minReplicas !== maxReplicas);
      setMinR(minReplicas);
      setMaxR(maxReplicas);
      setCpuTarget(cpuThreshold);
      setSelectedTier(null);
      setError("");
    }
  }, [open, currentReplicas, minReplicas, maxReplicas, cpuThreshold]);

  // Detect current tier
  const currentTier = RESOURCE_TIERS.find(
    (t) => t.cpuReq === currentCpuRequest && t.cpuLim === currentCpuLimit
  );

  async function handleApply() {
    setLoading(true);
    setError("");
    try {
      const tier = selectedTier ? RESOURCE_TIERS.find((t) => t.id === selectedTier) : null;
      const body: Record<string, unknown> = { replicas };
      if (hpaEnabled) {
        body.min_replicas = minR;
        body.max_replicas = maxR;
        body.cpu_threshold = cpuTarget;
      } else {
        body.min_replicas = replicas;
        body.max_replicas = replicas;
      }
      if (tier) {
        body.resource_cpu_request = tier.cpuReq;
        body.resource_cpu_limit = tier.cpuLim;
        body.resource_memory_request = tier.memReq;
        body.resource_memory_limit = tier.memLim;
      }
      await api.apps.update(tenantSlug, appSlug, body as Record<string, string>, accessToken);
      onSuccess();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scale failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Layers className="w-5 h-5 text-blue-500" /> Scale: {appSlug}
          </DialogTitle>
          <DialogDescription>Configure replicas, auto-scaling, and resources.</DialogDescription>
        </DialogHeader>

        <div className="space-y-5 mt-2">
          {/* Replicas */}
          <div>
            <label className="text-sm font-medium text-gray-700 dark:text-[#ccc] mb-2 block">Replicas</label>
            <div className="flex items-center gap-2">
              {REPLICA_PRESETS.map((n) => (
                <button
                  key={n}
                  type="button"
                  onClick={() => setReplicas(n)}
                  className={`w-10 h-10 rounded-lg text-sm font-semibold transition-colors ${
                    replicas === n
                      ? "bg-blue-600 text-white"
                      : "bg-gray-100 dark:bg-[#1a1a1a] text-gray-700 dark:text-[#ccc] hover:bg-gray-200 dark:hover:bg-[#222]"
                  }`}
                >
                  {n}
                </button>
              ))}
              <input
                type="number"
                min={1}
                max={20}
                value={replicas}
                onChange={(e) => setReplicas(Math.max(1, Math.min(20, parseInt(e.target.value) || 1)))}
                className="w-16 h-10 px-2 text-center rounded-lg border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0f0f0f] text-sm"
              />
            </div>
            {currentReplicas !== replicas && (
              <p className="text-xs text-blue-500 mt-1">
                {currentReplicas} → {replicas} replicas
              </p>
            )}
          </div>

          {/* Auto-scaling */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium text-gray-700 dark:text-[#ccc]">Auto-scaling (HPA)</label>
              <button
                type="button"
                onClick={() => setHpaEnabled(!hpaEnabled)}
                className={`relative w-10 h-5 rounded-full transition-colors ${
                  hpaEnabled ? "bg-blue-600" : "bg-gray-300 dark:bg-[#333]"
                }`}
              >
                <span className={`absolute w-4 h-4 rounded-full bg-white top-0.5 transition-transform ${
                  hpaEnabled ? "translate-x-5" : "translate-x-0.5"
                }`} />
              </button>
            </div>
            {hpaEnabled && (
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <span className="text-xs text-gray-500 dark:text-[#888]">Min</span>
                  <input type="number" min={1} max={maxR} value={minR} onChange={(e) => setMinR(parseInt(e.target.value) || 1)}
                    className="w-full mt-1 px-2 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0f0f0f]" />
                </div>
                <div>
                  <span className="text-xs text-gray-500 dark:text-[#888]">Max</span>
                  <input type="number" min={minR} max={50} value={maxR} onChange={(e) => setMaxR(parseInt(e.target.value) || 5)}
                    className="w-full mt-1 px-2 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0f0f0f]" />
                </div>
                <div>
                  <span className="text-xs text-gray-500 dark:text-[#888]">CPU Target</span>
                  <div className="flex items-center gap-1 mt-1">
                    <input type="number" min={10} max={100} value={cpuTarget} onChange={(e) => setCpuTarget(parseInt(e.target.value) || 70)}
                      className="w-full px-2 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0f0f0f]" />
                    <span className="text-xs text-gray-500">%</span>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Resource tier */}
          <div>
            <label className="text-sm font-medium text-gray-700 dark:text-[#ccc] mb-2 block">Resource Tier</label>
            <div className="grid grid-cols-3 gap-2">
              {RESOURCE_TIERS.map((tier) => {
                const Icon = tier.icon;
                const isActive = selectedTier === tier.id || (!selectedTier && currentTier?.id === tier.id);
                return (
                  <button
                    key={tier.id}
                    type="button"
                    onClick={() => setSelectedTier(tier.id)}
                    className={`p-3 rounded-lg border-2 text-left transition-all ${
                      isActive
                        ? "border-blue-500 bg-blue-50/50 dark:bg-blue-500/10"
                        : "border-gray-200 dark:border-[#2e2e2e] hover:border-gray-300"
                    }`}
                  >
                    <Icon className={`w-4 h-4 mb-1 ${isActive ? "text-blue-500" : "text-gray-400"}`} />
                    <div className="text-xs font-semibold text-gray-900 dark:text-white">{tier.label}</div>
                    <div className="text-[10px] text-gray-500 dark:text-[#888]">CPU: {tier.cpu}</div>
                    <div className="text-[10px] text-gray-500 dark:text-[#888]">RAM: {tier.mem}</div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Impact preview */}
          <div className="p-3 rounded-lg bg-gray-50 dark:bg-[#0a0a0a] border border-gray-100 dark:border-[#1e1e1e]">
            <div className="flex items-center gap-2 mb-2">
              <TrendingUp className="w-4 h-4 text-gray-400" />
              <span className="text-xs font-semibold text-gray-500 dark:text-[#999] uppercase">Impact Preview</span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div>
                <span className="text-gray-400">Pods:</span>{" "}
                <span className="font-mono text-gray-900 dark:text-white">{currentReplicas} → {replicas}</span>
              </div>
              <div>
                <span className="text-gray-400">CPU (total req):</span>{" "}
                <span className="font-mono text-gray-900 dark:text-white">
                  {currentReplicas}×{currentCpuRequest} → {replicas}×{(selectedTier ? RESOURCE_TIERS.find(t => t.id === selectedTier)?.cpuReq : currentCpuRequest) || currentCpuRequest}
                </span>
              </div>
            </div>
          </div>

          {error && (
            <p className="text-sm text-red-500 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-lg px-3 py-2">{error}</p>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <button onClick={onClose} className="px-4 py-2 text-sm text-gray-600 dark:text-[#999] hover:text-gray-900 dark:hover:text-white transition-colors">
              Cancel
            </button>
            <button
              onClick={handleApply}
              disabled={loading}
              className="inline-flex items-center gap-2 px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-semibold transition-colors"
            >
              {loading && <Loader2 className="w-4 h-4 animate-spin" />}
              Apply Changes
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
