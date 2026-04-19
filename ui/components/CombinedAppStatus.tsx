"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { CheckCircle2, AlertOctagon, Loader2, AlertTriangle, HelpCircle, RotateCcw } from "lucide-react";
import { api } from "@/lib/api";

type DeployStatus = "pending" | "building" | "built" | "deploying" | "running" | "failed" | null;
type LiveHealth = "Healthy" | "Degraded" | "Progressing" | "Missing" | "Unknown";

interface Props {
  tenantSlug: string;
  appSlug: string;
  deploymentStatus: DeployStatus;
  accessToken?: string;
  pollIntervalMs?: number;
}

interface LiveState {
  health: LiveHealth;
  sync: "Synced" | "OutOfSync" | "Unknown";
  reason: string;
  available: boolean;
}

/**
 * Single authoritative status badge on the app detail header.
 *
 * Pre-fix: two independent badges (cached deployment status + ArgoCD
 * LiveStatus) were rendered side by side. Combinations like "failed +
 * Progressing" or "running + Degraded" confused operators because the
 * customer sees two contradicting pills.
 *
 * This component collapses the two signals into one state machine:
 *
 *  | deployment | live              | shown         | color  |
 *  |------------|-------------------|---------------|--------|
 *  | running    | Healthy           | Running       | green  |
 *  | running    | Degraded          | Degraded      | red    |
 *  | running    | Progressing       | Progressing   | blue   |
 *  | failed     | Healthy           | Recovered     | green  |
 *  | failed     | Progressing       | Retrying      | amber  |
 *  | failed     | Degraded          | Failed        | red    |
 *  | building   | *                 | Building      | amber  |
 *  | deploying  | *                 | Deploying     | blue   |
 *  | pending    | *                 | Pending       | gray   |
 *
 * The one-line `reason` from ArgoCD is shown as a tooltip on hover so a
 * Degraded/Failed state is never opaque.
 *
 * Polls live-status internally at `pollIntervalMs` (default 10s) so the
 * badge self-updates without a parent-level setInterval.
 */
export function CombinedAppStatus({
  tenantSlug,
  appSlug,
  deploymentStatus,
  accessToken,
  pollIntervalMs = 10_000,
}: Props) {
  const [live, setLive] = useState<LiveState | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function tick() {
      try {
        const res = await api.observability.liveStatus(tenantSlug, appSlug, accessToken);
        if (!cancelled) setLive(res as LiveState);
      } catch {
        /* keep last known */
      }
    }
    void tick();
    const handle = setInterval(() => void tick(), pollIntervalMs);
    return () => {
      cancelled = true;
      clearInterval(handle);
    };
  }, [tenantSlug, appSlug, accessToken, pollIntervalMs]);

  const { label, variant, Icon, spin, tooltip } = resolve(deploymentStatus, live);

  return (
    <Badge
      variant={variant}
      title={tooltip}
      data-testid="combined-app-status"
      data-deployment={deploymentStatus ?? "null"}
      data-live={live?.health ?? "unknown"}
      className="inline-flex items-center gap-1.5"
    >
      <Icon className={`w-3 h-3 ${spin ? "animate-spin" : ""}`} />
      {label}
    </Badge>
  );
}

function resolve(
  d: DeployStatus,
  live: LiveState | null,
): {
  label: string;
  variant: "success" | "warning" | "destructive" | "secondary" | "default";
  Icon: typeof CheckCircle2;
  spin: boolean;
  tooltip: string;
} {
  // When live is unavailable, fall back to the cached deployment status.
  if (!live || !live.available) {
    return fallback(d);
  }

  const h = live.health;
  const reason = live.reason ? ` — ${live.reason}` : "";

  // Terminal successful state — prefer live signal
  if (h === "Healthy") {
    if (d === "failed") {
      // Most useful case for the user report: cache still says "failed"
      // but the cluster has actually recovered. Show it as Recovered so
      // the operator isn't scared by the stale red badge.
      return {
        label: "Recovered",
        variant: "success",
        Icon: CheckCircle2,
        spin: false,
        tooltip: `Cluster is Healthy. Previous deployment record shows ${d}${reason}.`,
      };
    }
    return {
      label: "Running",
      variant: "success",
      Icon: CheckCircle2,
      spin: false,
      tooltip: `Healthy (${live.sync})${reason}`,
    };
  }

  if (h === "Degraded") {
    return {
      label: "Degraded",
      variant: "destructive",
      Icon: AlertOctagon,
      spin: false,
      tooltip: `Degraded${reason}`,
    };
  }

  if (h === "Progressing") {
    if (d === "failed") {
      // User report L09: tier change or retry — cached failed + live
      // Progressing → we're retrying. Amber instead of red.
      return {
        label: "Retrying",
        variant: "warning",
        Icon: RotateCcw,
        spin: true,
        tooltip: `Retrying after a previous failure${reason}`,
      };
    }
    return {
      label: d === "building" ? "Building" : d === "deploying" ? "Deploying" : "Progressing",
      variant: "warning",
      Icon: Loader2,
      spin: true,
      tooltip: `In progress${reason}`,
    };
  }

  if (h === "Missing") {
    return {
      label: "Missing",
      variant: "destructive",
      Icon: AlertTriangle,
      spin: false,
      tooltip: `Application not found in ArgoCD${reason}`,
    };
  }

  // Unknown live — fall back to cached
  return fallback(d);
}

function fallback(d: DeployStatus) {
  switch (d) {
    case "running":
      return {
        label: "Running",
        variant: "success" as const,
        Icon: CheckCircle2,
        spin: false,
        tooltip: "Running (live status unavailable)",
      };
    case "failed":
      return {
        label: "Failed",
        variant: "destructive" as const,
        Icon: AlertOctagon,
        spin: false,
        tooltip: "Last deployment failed (live status unavailable)",
      };
    case "building":
      return {
        label: "Building",
        variant: "warning" as const,
        Icon: Loader2,
        spin: true,
        tooltip: "Building",
      };
    case "built":
      return {
        label: "Built",
        variant: "default" as const,
        Icon: CheckCircle2,
        spin: false,
        tooltip: "Image built, awaiting deploy",
      };
    case "deploying":
      return {
        label: "Deploying",
        variant: "warning" as const,
        Icon: Loader2,
        spin: true,
        tooltip: "Deploying",
      };
    case "pending":
      return {
        label: "Pending",
        variant: "secondary" as const,
        Icon: HelpCircle,
        spin: false,
        tooltip: "Pending",
      };
    default:
      return {
        label: "Unknown",
        variant: "secondary" as const,
        Icon: HelpCircle,
        spin: false,
        tooltip: "No deployment yet",
      };
  }
}
