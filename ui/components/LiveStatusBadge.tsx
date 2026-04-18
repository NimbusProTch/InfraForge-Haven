"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, AlertTriangle, Loader2, HelpCircle, AlertOctagon } from "lucide-react";
import { api } from "@/lib/api";

type Health = "Healthy" | "Degraded" | "Progressing" | "Missing" | "Unknown";

interface LiveStatus {
  health: Health;
  sync: "Synced" | "OutOfSync" | "Unknown";
  reason: string;
  phase: string;
  finished_at: string;
  available: boolean;
}

interface LiveStatusBadgeProps {
  tenantSlug: string;
  appSlug: string;
  accessToken?: string;
  intervalMs?: number;
}

const STYLE: Record<Health, { bg: string; text: string; icon: typeof CheckCircle2 }> = {
  Healthy: {
    bg: "bg-emerald-500/10 border-emerald-500/30 text-emerald-700 dark:text-emerald-400",
    text: "Healthy",
    icon: CheckCircle2,
  },
  Degraded: {
    bg: "bg-red-500/10 border-red-500/30 text-red-700 dark:text-red-400",
    text: "Degraded",
    icon: AlertOctagon,
  },
  Progressing: {
    bg: "bg-blue-500/10 border-blue-500/30 text-blue-700 dark:text-blue-400",
    text: "Progressing",
    icon: Loader2,
  },
  Missing: {
    bg: "bg-amber-500/10 border-amber-500/30 text-amber-700 dark:text-amber-400",
    text: "Missing",
    icon: AlertTriangle,
  },
  Unknown: {
    bg: "bg-gray-500/10 border-gray-500/30 text-gray-600 dark:text-gray-400",
    text: "Unknown",
    icon: HelpCircle,
  },
};

/**
 * Live health badge for an iyziops application. Polls
 * `GET /tenants/{slug}/apps/{app}/live-status` every `intervalMs` (default
 * 10s) and renders a colored pill backed by ArgoCD's actual health, with
 * the `reason` shown on hover.
 *
 * Returns nothing if ArgoCD is not reachable so the header stays clean
 * during local dev.
 */
export function LiveStatusBadge({
  tenantSlug,
  appSlug,
  accessToken,
  intervalMs = 10_000,
}: LiveStatusBadgeProps) {
  const [status, setStatus] = useState<LiveStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function tick() {
      try {
        const res = await api.observability.liveStatus(tenantSlug, appSlug, accessToken);
        if (!cancelled) setStatus(res);
      } catch {
        // network/auth — leave the previous value in place
      }
    }
    void tick();
    const handle = setInterval(() => void tick(), intervalMs);
    return () => {
      cancelled = true;
      clearInterval(handle);
    };
  }, [tenantSlug, appSlug, accessToken, intervalMs]);

  if (!status || !status.available) {
    return null;
  }

  const style = STYLE[status.health] ?? STYLE.Unknown;
  const Icon = style.icon;
  const tooltip = status.reason
    ? `${status.health} (${status.sync}) — ${status.reason}`
    : `${status.health} (${status.sync})`;

  return (
    <span
      data-testid="live-status-badge"
      data-health={status.health}
      data-sync={status.sync}
      title={tooltip}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${style.bg}`}
    >
      <Icon
        className={`w-3 h-3 ${status.health === "Progressing" ? "animate-spin" : ""}`}
      />
      <span>{style.text}</span>
      {status.sync === "OutOfSync" && status.health === "Healthy" && (
        <span className="ml-1 text-[10px] font-mono opacity-70">drift</span>
      )}
    </span>
  );
}
