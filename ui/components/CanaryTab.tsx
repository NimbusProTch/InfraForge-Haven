"use client";

import { useEffect, useState, useCallback } from "react";
import { api, type CanaryStatus } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { Badge } from "@/components/ui/badge";
import {
  Loader2,
  GitCompare,
  ArrowRight,
  CheckCircle2,
  RotateCcw,
  Zap,
  ArrowUpRight,
} from "lucide-react";

interface CanaryTabProps {
  tenantSlug: string;
  appSlug: string;
  accessToken?: string;
}

export default function CanaryTab({ tenantSlug, appSlug, accessToken }: CanaryTabProps) {
  const { error: toastError, success: toastSuccess } = useToast();
  const [canary, setCanary] = useState<CanaryStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState(false);
  const [promoting, setPromoting] = useState(false);
  const [rollingBack, setRollingBack] = useState(false);
  const [weight, setWeight] = useState(10);

  const loadCanary = useCallback(async () => {
    try {
      const c = await api.canary.status(tenantSlug, appSlug, accessToken);
      setCanary(c);
      if (c.canary_weight) setWeight(c.canary_weight);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [tenantSlug, appSlug, accessToken]);

  useEffect(() => {
    loadCanary();
  }, [loadCanary]);

  async function toggleCanary(enabled: boolean) {
    setUpdating(true);
    try {
      const result = await api.canary.set(tenantSlug, appSlug, {
        enabled,
        canary_weight: enabled ? weight : 0,
      }, accessToken);
      setCanary(result);
      toastSuccess(enabled ? "Canary deployment enabled" : "Canary deployment disabled");
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Failed to update canary");
    } finally {
      setUpdating(false);
    }
  }

  async function updateWeight() {
    setUpdating(true);
    try {
      const result = await api.canary.set(tenantSlug, appSlug, {
        enabled: true,
        canary_weight: weight,
      }, accessToken);
      setCanary(result);
      toastSuccess(`Traffic weight updated to ${weight}%`);
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Failed to update weight");
    } finally {
      setUpdating(false);
    }
  }

  async function promote() {
    if (!confirm("Promote canary to stable? This will replace the current stable deployment.")) return;
    setPromoting(true);
    try {
      await api.canary.promote(tenantSlug, appSlug, accessToken);
      await loadCanary();
      toastSuccess("Canary promoted to stable!");
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Failed to promote");
    } finally {
      setPromoting(false);
    }
  }

  async function rollback() {
    if (!confirm("Rollback canary? This will disable canary and restore 100% traffic to stable.")) return;
    setRollingBack(true);
    try {
      await api.canary.rollback(tenantSlug, appSlug, accessToken);
      await loadCanary();
      toastSuccess("Canary rolled back");
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Failed to rollback");
    } finally {
      setRollingBack(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-5 h-5 animate-spin text-zinc-600" />
      </div>
    );
  }

  const isEnabled = canary?.enabled ?? false;
  const stableWeight = 100 - (canary?.canary_weight ?? 0);

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <p className="text-sm text-zinc-500">Gradually shift traffic between stable and canary deployments</p>
        <Badge variant={isEnabled ? "success" : "secondary"}>
          {isEnabled ? "Active" : "Disabled"}
        </Badge>
      </div>

      {/* Traffic split visualization */}
      <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-5 mb-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-medium text-zinc-300">Traffic Distribution</h3>
        </div>

        {/* Visual bar */}
        <div className="w-full h-3 bg-zinc-800 rounded-full overflow-hidden flex mb-4">
          <div
            className="h-full bg-emerald-500 transition-all duration-500"
            style={{ width: `${stableWeight}%` }}
          />
          {isEnabled && (
            <div
              className="h-full bg-amber-500 transition-all duration-500"
              style={{ width: `${canary?.canary_weight ?? 0}%` }}
            />
          )}
        </div>

        {/* Labels */}
        <div className="grid grid-cols-2 gap-4">
          <div className="flex items-center gap-3">
            <div className="w-3 h-3 rounded-full bg-emerald-500" />
            <div>
              <p className="text-sm font-medium text-zinc-200">Stable</p>
              <p className="text-xs text-zinc-600 font-mono">
                {stableWeight}% traffic
                {canary?.stable_image && ` · ${canary.stable_image.slice(0, 12)}`}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className={`w-3 h-3 rounded-full ${isEnabled ? "bg-amber-500" : "bg-zinc-700"}`} />
            <div>
              <p className="text-sm font-medium text-zinc-200">Canary</p>
              <p className="text-xs text-zinc-600 font-mono">
                {isEnabled ? `${canary?.canary_weight ?? 0}%` : "0%"} traffic
                {canary?.canary_image && ` · ${canary.canary_image.slice(0, 12)}`}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Controls */}
      {!isEnabled ? (
        <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-5">
          <div className="flex items-center gap-3 mb-4">
            <GitCompare className="w-5 h-5 text-zinc-500" />
            <div>
              <h3 className="text-sm font-medium text-zinc-300">Enable Canary Deployments</h3>
              <p className="text-xs text-zinc-600 mt-0.5">
                Route a percentage of traffic to a new version before full rollout.
              </p>
            </div>
          </div>

          <div className="mb-4">
            <label className="block text-xs font-medium text-zinc-400 mb-1.5">
              Initial canary weight: <span className="text-zinc-200">{weight}%</span>
            </label>
            <input
              type="range"
              min={1}
              max={50}
              value={weight}
              onChange={(e) => setWeight(Number(e.target.value))}
              className="w-full h-1.5 bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-amber-500"
            />
            <div className="flex justify-between text-xs text-zinc-600 mt-1">
              <span>1%</span>
              <span>50%</span>
            </div>
          </div>

          <button
            onClick={() => toggleCanary(true)}
            disabled={updating}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-sm font-medium transition-colors disabled:opacity-50"
          >
            {updating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
            Enable Canary
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Weight slider */}
          <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-5">
            <label className="block text-xs font-medium text-zinc-400 mb-2">
              Canary traffic weight: <span className="text-amber-400 font-mono">{weight}%</span>
            </label>
            <div className="flex items-center gap-3">
              <input
                type="range"
                min={1}
                max={100}
                value={weight}
                onChange={(e) => setWeight(Number(e.target.value))}
                className="flex-1 h-1.5 bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-amber-500"
              />
              <button
                onClick={updateWeight}
                disabled={updating || weight === (canary?.canary_weight ?? 0)}
                className="px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-xs font-medium text-zinc-300 transition-colors disabled:opacity-30"
              >
                {updating ? <Loader2 className="w-3 h-3 animate-spin" /> : "Apply"}
              </button>
            </div>
          </div>

          {/* Action buttons */}
          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={promote}
              disabled={promoting}
              className="flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-emerald-600/10 border border-emerald-600/20 hover:bg-emerald-600/20 text-emerald-400 text-sm font-medium transition-colors disabled:opacity-50"
            >
              {promoting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <ArrowUpRight className="w-4 h-4" />
              )}
              Promote to Stable
            </button>
            <button
              onClick={rollback}
              disabled={rollingBack}
              className="flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-red-600/10 border border-red-600/20 hover:bg-red-600/20 text-red-400 text-sm font-medium transition-colors disabled:opacity-50"
            >
              {rollingBack ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <RotateCcw className="w-4 h-4" />
              )}
              Rollback Canary
            </button>
          </div>

          {/* Disable */}
          <button
            onClick={() => toggleCanary(false)}
            disabled={updating}
            className="w-full text-center text-xs text-zinc-600 hover:text-zinc-400 py-2 transition-colors"
          >
            Disable canary deployments
          </button>
        </div>
      )}
    </div>
  );
}
