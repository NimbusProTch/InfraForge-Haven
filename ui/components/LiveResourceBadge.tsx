"use client";

import { useEffect, useState } from "react";
import { Cpu, MemoryStick } from "lucide-react";
import { api } from "@/lib/api";

interface LiveResourceBadgeProps {
  tenantSlug: string;
  appSlug: string;
  accessToken?: string;
  /** Polling interval in milliseconds. Defaults to 10s. */
  intervalMs?: number;
}

/**
 * Compact CPU + memory pill that polls /observability/pods every `intervalMs`
 * and renders the *averaged* usage across pods.
 *
 * Lives at the top of the app detail page so resource health is visible from
 * every tab, not just from "Observability". Backed by the cluster's
 * built-in `rke2-metrics-server` (apiserver group `metrics.k8s.io`).
 */
export function LiveResourceBadge({
  tenantSlug,
  appSlug,
  accessToken,
  intervalMs = 10_000,
}: LiveResourceBadgeProps) {
  const [cpu, setCpu] = useState<number | null>(null);
  const [memory, setMemory] = useState<number | null>(null);
  const [available, setAvailable] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function tick() {
      try {
        const res = await api.observability.pods(tenantSlug, appSlug, accessToken);
        if (cancelled) return;
        if (!res.k8s_available) {
          setAvailable(false);
          return;
        }
        setAvailable(true);
        const pods = res.pods ?? [];
        if (pods.length === 0) {
          setCpu(null);
          setMemory(null);
          return;
        }
        const cpuAvg = Math.round(
          pods.reduce((s, p) => s + (p.cpu_usage ?? 0), 0) / pods.length
        );
        const memAvg = Math.round(
          pods.reduce((s, p) => s + (p.memory_usage ?? 0), 0) / pods.length
        );
        setCpu(cpuAvg > 0 ? cpuAvg : null);
        setMemory(memAvg > 0 ? memAvg : null);
      } catch {
        // Network/auth errors — keep the last known value
      }
    }

    void tick();
    const handle = setInterval(() => void tick(), intervalMs);
    return () => {
      cancelled = true;
      clearInterval(handle);
    };
  }, [tenantSlug, appSlug, accessToken, intervalMs]);

  if (available === false) {
    return null;
  }

  return (
    <div
      data-testid="live-resource-badge"
      className="inline-flex items-center gap-3 rounded-lg border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-800/60 px-3 py-1.5 text-xs"
      title="Live CPU + memory averaged across pods (refreshed every 10s)"
    >
      <span className="inline-flex items-center gap-1.5">
        <Cpu className="w-3 h-3 text-blue-500" />
        <span className="font-mono text-gray-700 dark:text-zinc-200">
          {cpu === null ? "—" : `${cpu}%`}
        </span>
      </span>
      <span className="text-gray-300 dark:text-zinc-700">|</span>
      <span className="inline-flex items-center gap-1.5">
        <MemoryStick className="w-3 h-3 text-purple-500" />
        <span className="font-mono text-gray-700 dark:text-zinc-200">
          {memory === null ? "—" : `${memory}%`}
        </span>
      </span>
    </div>
  );
}
