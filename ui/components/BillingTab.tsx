"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { useToast } from "@/components/Toast";
import {
  Loader2,
  Cpu,
  MemoryStick,
  HardDrive,
  Hammer,
  TrendingUp,
  Zap,
} from "lucide-react";

interface UsageSummary {
  tier: string;
  current_period: {
    cpu_hours: number;
    memory_gb_hours: number;
    storage_gb_months: number;
    build_minutes: number;
  };
  limits: {
    cpu_hours: number | null;
    memory_gb_hours: number | null;
    storage_gb_months: number | null;
    build_minutes: number | null;
  };
  usage_pct: {
    cpu: number | null;
    memory: number | null;
    storage: number | null;
    builds: number | null;
  };
  history: Array<{
    period: string;
    cpu_hours: number;
    memory_gb_hours: number;
    storage_gb_months: number;
    build_minutes: number;
  }>;
}

function UsageBar({ label, icon: Icon, used, limit, unit, color }: {
  label: string;
  icon: typeof Cpu;
  used: number;
  limit: number | null;
  unit: string;
  color: string;
}) {
  const pct = limit ? Math.min((used / limit) * 100, 100) : null;
  const barColor = pct && pct > 80 ? "bg-red-500" : pct && pct > 60 ? "bg-amber-500" : color;

  return (
    <div className="bg-white dark:bg-zinc-900/50 border border-gray-200 dark:border-zinc-800 rounded-xl shadow-sm p-4">
      <div className="flex items-center gap-2 mb-3">
        <Icon className={`w-4 h-4 ${color.replace("bg-", "text-")}`} />
        <span className="text-xs font-medium text-gray-500 dark:text-zinc-400">{label}</span>
      </div>
      <div className="flex items-baseline gap-1.5 mb-2">
        <span className="text-xl font-bold text-gray-900 dark:text-zinc-100">{(used ?? 0).toFixed(1)}</span>
        {limit && (
          <span className="text-xs text-gray-400 dark:text-zinc-600">/ {limit} {unit}</span>
        )}
        {!limit && (
          <span className="text-xs text-gray-400 dark:text-zinc-600">{unit}</span>
        )}
      </div>
      {pct !== null ? (
        <div className="w-full h-1.5 bg-gray-100 dark:bg-zinc-800 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${barColor}`}
            style={{ width: `${pct}%` }}
          />
        </div>
      ) : (
        <div className="flex items-center gap-1 text-xs text-gray-400 dark:text-zinc-600">
          <Zap className="w-3 h-3" />
          Unlimited
        </div>
      )}
      {pct !== null && (
        <p className="text-xs text-gray-400 dark:text-zinc-600 mt-1">{pct.toFixed(0)}% used</p>
      )}
    </div>
  );
}

interface BillingTabProps {
  tenantSlug: string;
  accessToken?: string;
}

export default function BillingTab({ tenantSlug, accessToken }: BillingTabProps) {
  const { error: toastError } = useToast();
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [loading, setLoading] = useState(true);

  const loadUsage = useCallback(async () => {
    try {
      const u = await api.billing.usage(tenantSlug, undefined, accessToken);
      setUsage(u as unknown as UsageSummary);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [tenantSlug, accessToken]);

  useEffect(() => {
    loadUsage();
  }, [loadUsage]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-5 h-5 animate-spin text-gray-400 dark:text-zinc-600" />
      </div>
    );
  }

  if (!usage || !usage.current_period) {
    return (
      <div className="text-center py-16 border border-dashed border-gray-200 dark:border-zinc-800 rounded-xl">
        <TrendingUp className="w-8 h-8 mx-auto mb-2 text-gray-400 dark:text-zinc-700" />
        <p className="text-sm text-gray-500 dark:text-zinc-500">No usage data for this billing period yet.</p>
        <p className="text-xs text-gray-400 dark:text-zinc-600 mt-1">Usage tracking begins when apps are deployed.</p>
      </div>
    );
  }

  const cp = usage.current_period;
  const lm = usage.limits ?? { cpu_hours: null, memory_gb_hours: null, storage_gb_months: null, build_minutes: null };

  return (
    <div>
      {/* Tier badge */}
      <div className="flex items-center justify-between mb-5">
        <p className="text-sm text-gray-500 dark:text-zinc-500">Resource usage for the current billing period</p>
        <div className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-violet-600/10 border border-violet-600/20 text-violet-400 text-xs font-medium">
          <Zap className="w-3 h-3" />
          {usage.tier.charAt(0).toUpperCase() + usage.tier.slice(1)} Plan
        </div>
      </div>

      {/* Usage cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        <UsageBar label="CPU" icon={Cpu} used={cp.cpu_hours} limit={lm.cpu_hours} unit="hours" color="bg-blue-500" />
        <UsageBar label="Memory" icon={MemoryStick} used={cp.memory_gb_hours} limit={lm.memory_gb_hours} unit="GB·h" color="bg-violet-500" />
        <UsageBar label="Storage" icon={HardDrive} used={cp.storage_gb_months} limit={lm.storage_gb_months} unit="GB·mo" color="bg-cyan-500" />
        <UsageBar label="Builds" icon={Hammer} used={cp.build_minutes} limit={lm.build_minutes} unit="min" color="bg-amber-500" />
      </div>

      {/* History */}
      {usage.history && usage.history.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-gray-700 dark:text-zinc-300 mb-3">Usage History</h3>
          <div className="bg-white dark:bg-zinc-900/50 border border-gray-200 dark:border-zinc-800 rounded-xl shadow-sm overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-200 dark:border-zinc-800">
                  <th className="text-left text-xs font-medium text-gray-400 dark:text-zinc-600 px-4 py-2.5">Period</th>
                  <th className="text-right text-xs font-medium text-gray-400 dark:text-zinc-600 px-4 py-2.5">CPU (h)</th>
                  <th className="text-right text-xs font-medium text-gray-400 dark:text-zinc-600 px-4 py-2.5">Memory (GB·h)</th>
                  <th className="text-right text-xs font-medium text-gray-400 dark:text-zinc-600 px-4 py-2.5">Storage (GB·mo)</th>
                  <th className="text-right text-xs font-medium text-gray-400 dark:text-zinc-600 px-4 py-2.5">Builds (min)</th>
                </tr>
              </thead>
              <tbody>
                {usage.history.map((row) => (
                  <tr key={row.period} className="border-b border-gray-200 dark:border-zinc-800/50 last:border-0 hover:bg-gray-100 dark:hover:bg-zinc-800/30">
                    <td className="text-sm text-gray-700 dark:text-zinc-300 px-4 py-2.5 font-mono">{row.period}</td>
                    <td className="text-sm text-gray-500 dark:text-zinc-400 px-4 py-2.5 text-right">{(row.cpu_hours ?? 0).toFixed(1)}</td>
                    <td className="text-sm text-gray-500 dark:text-zinc-400 px-4 py-2.5 text-right">{(row.memory_gb_hours ?? 0).toFixed(1)}</td>
                    <td className="text-sm text-gray-500 dark:text-zinc-400 px-4 py-2.5 text-right">{(row.storage_gb_months ?? 0).toFixed(1)}</td>
                    <td className="text-sm text-gray-500 dark:text-zinc-400 px-4 py-2.5 text-right">{(row.build_minutes ?? 0).toFixed(0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
