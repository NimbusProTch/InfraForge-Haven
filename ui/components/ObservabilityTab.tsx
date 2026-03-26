"use client";

import { useEffect, useState, useRef } from "react";
import { getLogsUrl, Deployment, api } from "@/lib/api";

interface ObservabilityTabProps {
  tenantSlug: string;
  appSlug: string;
  deployments: Deployment[];
}

export default function ObservabilityTab({ tenantSlug, appSlug, deployments }: ObservabilityTabProps) {
  const [logs, setLogs] = useState<string[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const startStream = async () => {
    if (streaming) return;
    setStreaming(true);
    setLogs([]);
    abortRef.current = new AbortController();

    try {
      const url = getLogsUrl(tenantSlug, appSlug);
      const response = await fetch(url, { signal: abortRef.current.signal });
      const reader = response.body?.getReader();
      if (!reader) return;

      const decoder = new TextDecoder();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const text = decoder.decode(value);
        const lines = text.split("\n").filter((l) => l.startsWith("data: ")).map((l) => l.slice(6));
        if (lines.some((l) => l === "[end]")) {
          setLogs((prev) => [...prev, ...lines.filter((l) => l !== "[end]")]);
          break;
        }
        setLogs((prev) => [...prev, ...lines]);
      }
    } catch {
      // Aborted or network error
    } finally {
      setStreaming(false);
    }
  };

  const stopStream = () => {
    abortRef.current?.abort();
    setStreaming(false);
  };

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  // Auto-refresh effect
  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(startStream, 10000);
    return () => clearInterval(interval);
  }, [autoRefresh]);

  const latestDeployment = deployments[0];

  return (
    <div className="space-y-6">
      {/* Deployment Status */}
      <div className="rounded-lg border p-4">
        <h3 className="text-sm font-semibold mb-3">Latest Deployment</h3>
        {latestDeployment ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <p className="text-xs text-muted-foreground">Status</p>
              <StatusDot status={latestDeployment.status} />
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Commit</p>
              <p className="text-sm font-mono">{latestDeployment.commit_sha.slice(0, 7)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Image</p>
              <p className="text-sm font-mono truncate">{latestDeployment.image_tag?.split(":").pop() || "-"}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Time</p>
              <p className="text-sm">{new Date(latestDeployment.created_at).toLocaleString()}</p>
            </div>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No deployments yet</p>
        )}
      </div>

      {/* Metrics (placeholder — connect to Prometheus/Grafana later) */}
      <div className="rounded-lg border p-4">
        <h3 className="text-sm font-semibold mb-3">Resource Usage</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <MetricBar label="CPU" value={23} unit="%" color="bg-blue-500" />
          <MetricBar label="Memory" value={45} unit="%" color="bg-green-500" />
        </div>
        <p className="text-xs text-muted-foreground mt-2">
          Live metrics available when connected to Prometheus. Showing mock data.
        </p>
      </div>

      {/* Log Terminal */}
      <div className="rounded-lg border">
        <div className="flex items-center justify-between p-3 border-b">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold">Logs</h3>
            {streaming && (
              <span className="flex items-center gap-1 text-xs text-green-500">
                <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                Live
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-1 text-xs">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                className="rounded"
              />
              Auto-refresh
            </label>
            {!streaming ? (
              <button onClick={startStream} className="text-xs px-3 py-1 rounded bg-primary text-primary-foreground">
                Stream Logs
              </button>
            ) : (
              <button onClick={stopStream} className="text-xs px-3 py-1 rounded bg-destructive text-destructive-foreground">
                Stop
              </button>
            )}
            <button onClick={() => setLogs([])} className="text-xs px-3 py-1 rounded border">
              Clear
            </button>
          </div>
        </div>
        <div className="bg-black text-green-400 p-4 font-mono text-xs max-h-96 overflow-y-auto">
          {logs.length === 0 ? (
            <p className="text-gray-500">Click &quot;Stream Logs&quot; to view application logs...</p>
          ) : (
            logs.map((line, i) => (
              <div key={i} className="whitespace-pre-wrap">{line}</div>
            ))
          )}
          <div ref={logsEndRef} />
        </div>
      </div>

      {/* Deployment History */}
      <div className="rounded-lg border p-4">
        <h3 className="text-sm font-semibold mb-3">Deployment History</h3>
        <div className="space-y-2">
          {deployments.slice(0, 10).map((dep) => (
            <div key={dep.id} className="flex items-center justify-between py-2 border-b last:border-0">
              <div className="flex items-center gap-2">
                <StatusDot status={dep.status} />
                <span className="text-sm font-mono">{dep.commit_sha.slice(0, 7)}</span>
              </div>
              <span className="text-xs text-muted-foreground">
                {new Date(dep.created_at).toLocaleString()}
              </span>
            </div>
          ))}
          {deployments.length === 0 && (
            <p className="text-sm text-muted-foreground">No deployment history</p>
          )}
        </div>
      </div>
    </div>
  );
}

function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    running: "bg-green-500",
    building: "bg-yellow-500",
    deploying: "bg-blue-500",
    pending: "bg-gray-400",
    failed: "bg-red-500",
  };
  return (
    <div className="flex items-center gap-1.5">
      <span className={`w-2 h-2 rounded-full ${colors[status] || "bg-gray-400"}`} />
      <span className="text-sm capitalize">{status}</span>
    </div>
  );
}

function MetricBar({ label, value, unit, color }: { label: string; value: number; unit: string; color: string }) {
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span>{label}</span>
        <span>{value}{unit}</span>
      </div>
      <div className="h-2 rounded-full bg-muted overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}
