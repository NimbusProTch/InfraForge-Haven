"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Badge } from "@/components/ui/badge";
import { api, type PodInfo, type AppEvent } from "@/lib/api";
import type { Deployment } from "@/lib/api";
import {
  Activity,
  AlertTriangle,
  Clock,
  Cpu,
  HardDrive,
  MemoryStick,
  Pause,
  Play,
  RefreshCw,
  Terminal,
} from "lucide-react";

interface ObservabilityTabProps {
  tenantSlug: string;
  appSlug: string;
  appName: string;
  deployments: Deployment[];
  logs: string;
  streaming: boolean;
  onStartLogs: () => void;
  onStopLogs: () => void;
  accessToken?: string;
}

const POD_STATUS_COLORS: Record<string, string> = {
  Running: "bg-emerald-500",
  Pending: "bg-yellow-500 animate-pulse",
  CrashLoopBackOff: "bg-red-500 animate-pulse",
  Error: "bg-red-500",
  Terminated: "bg-gray-500",
  OOMKilled: "bg-red-500",
  ContainerCreating: "bg-yellow-500 animate-pulse",
};

const POD_STATUS_BADGE: Record<string, "success" | "warning" | "destructive" | "secondary"> = {
  Running: "success",
  Pending: "warning",
  CrashLoopBackOff: "destructive",
  Error: "destructive",
  Terminated: "secondary",
  OOMKilled: "destructive",
  ContainerCreating: "warning",
};

function UsageBar({ percent, color }: { percent: number; color: string }) {
  return (
    <div className="w-full h-1.5 rounded-full bg-gray-200 dark:bg-[#2a2a2a] overflow-hidden">
      <div
        className={`h-full rounded-full transition-all duration-500 ${color}`}
        style={{ width: `${Math.min(100, Math.max(0, percent))}%` }}
      />
    </div>
  );
}

export default function ObservabilityTab({
  tenantSlug,
  appSlug,
  appName,
  deployments,
  logs,
  streaming,
  onStartLogs,
  onStopLogs,
  accessToken,
}: ObservabilityTabProps) {
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [pods, setPods] = useState<PodInfo[]>([]);
  const [events, setEvents] = useState<AppEvent[]>([]);
  const [k8sAvailable, setK8sAvailable] = useState<boolean | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<Date>(new Date());
  const refreshRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);

  const latestDeployment = deployments[0];

  const refreshData = useCallback(async () => {
    try {
      const [podsRes, eventsRes] = await Promise.all([
        api.observability.pods(tenantSlug, appSlug, accessToken),
        api.observability.events(tenantSlug, appSlug, accessToken),
      ]);
      setPods(podsRes.pods);
      setEvents(eventsRes.events);
      setK8sAvailable(podsRes.k8s_available);
      setLastRefreshed(new Date());
    } catch (err) {
      // API not reachable — don't crash the tab
      console.error("Observability fetch error:", err);
    }
  }, [tenantSlug, appSlug, accessToken]);

  useEffect(() => {
    void refreshData();
  }, [refreshData]);

  useEffect(() => {
    if (autoRefresh) {
      refreshRef.current = setInterval(() => void refreshData(), 5000);
    }
    return () => {
      if (refreshRef.current) {
        clearInterval(refreshRef.current);
        refreshRef.current = null;
      }
    };
  }, [autoRefresh, refreshData]);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const avgCpu =
    pods.length > 0
      ? Math.round(pods.reduce((s, p) => s + (p.cpu_usage ?? 0), 0) / pods.length)
      : 0;
  const avgMemory =
    pods.length > 0
      ? Math.round(pods.reduce((s, p) => s + (p.memory_usage ?? 0), 0) / pods.length)
      : 0;

  const recentDeployments = deployments.slice(0, 8);
  const warningEvents = events.filter((e) => e.type === "Warning");

  return (
    <div className="space-y-6">
      {/* Header with auto-refresh toggle */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-gray-400 dark:text-[#555]" />
          <span className="text-xs text-gray-500 dark:text-[#666]">
            Last refreshed: {lastRefreshed.toLocaleTimeString()}
          </span>
          {k8sAvailable === false && (
            <span className="text-xs text-amber-500">· cluster unavailable</span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => void refreshData()}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs text-gray-500 dark:text-[#666] hover:text-gray-700 dark:hover:text-[#999] border border-gray-200 dark:border-[#2e2e2e] hover:border-gray-400 dark:hover:border-[#444] transition-colors"
          >
            <RefreshCw className="w-3 h-3" />
            Refresh
          </button>
          <label className="flex items-center gap-2 cursor-pointer">
            <div className="relative">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-8 h-4 rounded-full bg-gray-200 dark:bg-[#2a2a2a] peer-checked:bg-emerald-600 transition-colors" />
              <div className="absolute top-0.5 left-0.5 w-3 h-3 rounded-full bg-white shadow transition-transform peer-checked:translate-x-4" />
            </div>
            <span className="text-xs text-gray-500 dark:text-[#666]">Auto-refresh (5s)</span>
          </label>
        </div>
      </div>

      {/* Overview metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg px-4 py-3">
          <div className="flex items-center gap-1.5 mb-2">
            <Cpu className="w-3 h-3 text-blue-500" />
            <span className="text-xs text-gray-500 dark:text-[#666]">Avg CPU</span>
          </div>
          <p className="text-lg font-semibold text-gray-900 dark:text-white font-mono">
            {avgCpu > 0 ? `${avgCpu}%` : "—"}
          </p>
          {avgCpu > 0 && <UsageBar percent={avgCpu} color="bg-blue-500" />}
        </div>
        <div className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg px-4 py-3">
          <div className="flex items-center gap-1.5 mb-2">
            <MemoryStick className="w-3 h-3 text-purple-500" />
            <span className="text-xs text-gray-500 dark:text-[#666]">Avg Memory</span>
          </div>
          <p className="text-lg font-semibold text-gray-900 dark:text-white font-mono">
            {avgMemory > 0 ? `${avgMemory}%` : "—"}
          </p>
          {avgMemory > 0 && <UsageBar percent={avgMemory} color="bg-purple-500" />}
        </div>
        <div className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg px-4 py-3">
          <div className="flex items-center gap-1.5 mb-2">
            <HardDrive className="w-3 h-3 text-emerald-500" />
            <span className="text-xs text-gray-500 dark:text-[#666]">Pods</span>
          </div>
          <p className="text-lg font-semibold text-gray-900 dark:text-white font-mono">
            {pods.filter((p) => p.status === "Running").length}/{pods.length}
          </p>
          <p className="text-[10px] text-gray-400 dark:text-[#555]">ready</p>
        </div>
        <div className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg px-4 py-3">
          <div className="flex items-center gap-1.5 mb-2">
            <Clock className="w-3 h-3 text-amber-500" />
            <span className="text-xs text-gray-500 dark:text-[#666]">Deployments</span>
          </div>
          <p className="text-lg font-semibold text-gray-900 dark:text-white font-mono">
            {deployments.length}
          </p>
          <p className="text-[10px] text-gray-400 dark:text-[#555]">total</p>
        </div>
      </div>

      {/* Pod Status */}
      <div className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-200 dark:border-[#222]">
          <h4 className="text-sm font-semibold text-gray-900 dark:text-white">Pod Status</h4>
        </div>
        {pods.length === 0 ? (
          <div className="px-4 py-8 text-center text-gray-400 dark:text-[#555] text-sm">
            {k8sAvailable === false
              ? "Kubernetes cluster unavailable"
              : latestDeployment?.status === "running"
              ? "Loading pods..."
              : "No pods running"}
          </div>
        ) : (
          <div className="divide-y divide-gray-100 dark:divide-[#1e1e1e]">
            {/* Table header */}
            <div className="grid grid-cols-[1fr_120px_80px_60px_140px_140px] gap-3 px-4 py-2 text-xs font-medium text-gray-500 dark:text-[#666] uppercase tracking-wider">
              <span>Pod</span>
              <span>Status</span>
              <span>Restarts</span>
              <span>Age</span>
              <span>CPU</span>
              <span>Memory</span>
            </div>
            {pods.map((pod) => (
              <div
                key={pod.name}
                className="grid grid-cols-[1fr_120px_80px_60px_140px_140px] gap-3 px-4 py-2.5 items-center"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <div
                    className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                      POD_STATUS_COLORS[pod.status] ?? "bg-gray-500"
                    }`}
                  />
                  <span className="text-xs font-mono text-gray-700 dark:text-[#ccc] truncate">
                    {pod.name}
                  </span>
                </div>
                <Badge
                  variant={POD_STATUS_BADGE[pod.status] ?? "secondary"}
                  className="text-[10px] w-fit"
                >
                  {pod.status}
                </Badge>
                <span
                  className={`text-xs font-mono ${
                    pod.restarts > 0 ? "text-red-500" : "text-gray-500 dark:text-[#666]"
                  }`}
                >
                  {pod.restarts}
                </span>
                <span className="text-xs text-gray-500 dark:text-[#666]">{pod.age}</span>
                {/* CPU */}
                <div className="space-y-1">
                  {pod.cpu_value ? (
                    <>
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-mono text-gray-500 dark:text-[#666]">
                          {pod.cpu_value}
                        </span>
                        {pod.cpu_usage !== null && (
                          <span className="text-[10px] font-mono text-gray-400 dark:text-[#555]">
                            {pod.cpu_usage}%
                          </span>
                        )}
                      </div>
                      {pod.cpu_usage !== null && (
                        <UsageBar
                          percent={pod.cpu_usage}
                          color={pod.cpu_usage > 80 ? "bg-red-500" : "bg-blue-500"}
                        />
                      )}
                    </>
                  ) : (
                    <span className="text-[10px] text-gray-400 dark:text-[#555]">—</span>
                  )}
                </div>
                {/* Memory */}
                <div className="space-y-1">
                  {pod.memory_value ? (
                    <>
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-mono text-gray-500 dark:text-[#666]">
                          {pod.memory_value}
                        </span>
                        {pod.memory_usage !== null && (
                          <span className="text-[10px] font-mono text-gray-400 dark:text-[#555]">
                            {pod.memory_usage}%
                          </span>
                        )}
                      </div>
                      {pod.memory_usage !== null && (
                        <UsageBar
                          percent={pod.memory_usage}
                          color={pod.memory_usage > 80 ? "bg-red-500" : "bg-purple-500"}
                        />
                      )}
                    </>
                  ) : (
                    <span className="text-[10px] text-gray-400 dark:text-[#555]">—</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Recent Logs */}
      <div className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-[#222]">
          <div className="flex items-center gap-2">
            <Terminal className="w-3.5 h-3.5 text-gray-400 dark:text-[#555]" />
            <h4 className="text-sm font-semibold text-gray-900 dark:text-white">Recent Logs</h4>
            {streaming && (
              <span className="flex items-center gap-1.5 text-xs text-emerald-500">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                live
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {!streaming ? (
              <button
                onClick={onStartLogs}
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-900/20 transition-colors"
              >
                <Play className="w-3 h-3" />
                Stream
              </button>
            ) : (
              <button
                onClick={onStopLogs}
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
              >
                <Pause className="w-3 h-3" />
                Stop
              </button>
            )}
          </div>
        </div>
        <div className="bg-[#0a0a0a]">
          <pre className="p-4 text-xs font-mono text-emerald-400/80 overflow-auto max-h-[250px] whitespace-pre-wrap break-all leading-relaxed">
            {logs || `# Waiting for log data from ${appName}...\n# Click "Stream" to start receiving live logs.\n`}
            <div ref={logsEndRef} />
          </pre>
        </div>
      </div>

      {/* K8s Events (Warning events only) */}
      {warningEvents.length > 0 && (
        <div className="bg-white dark:bg-[#141414] border border-amber-200 dark:border-amber-900/40 rounded-lg overflow-hidden">
          <div className="px-4 py-3 border-b border-amber-200 dark:border-amber-900/40 flex items-center gap-2">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
            <h4 className="text-sm font-semibold text-gray-900 dark:text-white">
              Warning Events
            </h4>
            <span className="text-xs text-amber-500 font-mono">{warningEvents.length}</span>
          </div>
          <div className="divide-y divide-gray-100 dark:divide-[#1e1e1e]">
            {warningEvents.slice(0, 5).map((ev, i) => (
              <div key={i} className="px-4 py-2.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <span className="text-xs font-medium text-amber-500">{ev.reason}</span>
                    <span className="text-xs text-gray-400 dark:text-[#555] ml-2 font-mono">
                      {ev.object_name}
                    </span>
                    <p className="text-xs text-gray-600 dark:text-[#888] mt-0.5 break-words">
                      {ev.message}
                    </p>
                  </div>
                  <div className="text-right shrink-0">
                    {ev.count > 1 && (
                      <span className="text-[10px] text-gray-400 dark:text-[#555]">
                        ×{ev.count}
                      </span>
                    )}
                    {ev.last_time && (
                      <p className="text-[10px] text-gray-400 dark:text-[#555]">
                        {new Date(ev.last_time).toLocaleTimeString()}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Deployment History Timeline */}
      <div className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-200 dark:border-[#222]">
          <h4 className="text-sm font-semibold text-gray-900 dark:text-white">
            Deployment History
          </h4>
        </div>
        {recentDeployments.length === 0 ? (
          <div className="px-4 py-8 text-center text-gray-400 dark:text-[#555] text-sm">
            No deployments yet
          </div>
        ) : (
          <div className="px-4 py-3">
            <div className="relative">
              {/* Timeline line */}
              <div className="absolute left-[7px] top-2 bottom-2 w-px bg-gray-200 dark:bg-[#2a2a2a]" />
              <div className="space-y-3">
                {recentDeployments.map((d, i) => {
                  const dotColor =
                    d.status === "running"
                      ? "bg-emerald-500"
                      : d.status === "failed"
                      ? "bg-red-500"
                      : d.status === "building" || d.status === "deploying"
                      ? "bg-blue-500 animate-pulse"
                      : "bg-gray-400";

                  return (
                    <div key={d.id} className="flex items-start gap-3 relative">
                      <div
                        className={`w-[15px] h-[15px] rounded-full border-2 border-white dark:border-[#141414] ${dotColor} shrink-0 z-10 mt-0.5`}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-xs font-mono text-gray-700 dark:text-[#ccc]">
                            {d.commit_sha ? d.commit_sha.slice(0, 7) : "manual"}
                          </span>
                          <Badge
                            variant={
                              d.status === "running"
                                ? "success"
                                : d.status === "failed"
                                ? "destructive"
                                : d.status === "building" || d.status === "deploying"
                                ? "warning"
                                : "secondary"
                            }
                            className="text-[10px]"
                          >
                            {d.status}
                          </Badge>
                          {i === 0 && d.status === "running" && (
                            <span className="text-[10px] font-medium text-emerald-500">
                              current
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-gray-400 dark:text-[#555] mt-0.5">
                          {new Date(d.created_at).toLocaleString()}
                          {d.image_tag && (
                            <span className="ml-2 font-mono text-[10px] text-gray-400 dark:text-[#444]">
                              {d.image_tag.split(":").pop()}
                            </span>
                          )}
                        </p>
                        {d.error_message && (
                          <p className="text-xs text-red-400 mt-1 truncate max-w-md">
                            {d.error_message}
                          </p>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
