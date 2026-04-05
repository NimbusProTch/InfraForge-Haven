"use client";

import { useState, useEffect, useCallback } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Loader2,
  RefreshCw,
  Server,
  Zap,
} from "lucide-react";
import { api, type QueueStatus } from "@/lib/api";

export default function QueueDashboardPage() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const [queueStatus, setQueueStatus] = useState<QueueStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<Date>(new Date());
  const [autoRefresh, setAutoRefresh] = useState(true);

  const accessToken = (session as typeof session & { accessToken?: string })?.accessToken;

  useEffect(() => {
    if (status === "unauthenticated") router.push("/auth/signin");
  }, [status, router]);

  const loadStatus = useCallback(async () => {
    if (status !== "authenticated") return;
    try {
      const s = await api.platform.queueStatus(accessToken);
      setQueueStatus(s);
      // Check if API returned an error_message (Redis down)
      if (s.error_message) {
        setErrorMsg(s.error_message);
      } else {
        setErrorMsg(null);
      }
      setLastRefreshed(new Date());
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to connect to platform API");
      setQueueStatus(null);
    } finally {
      setLoading(false);
    }
  }, [status, accessToken]);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => void loadStatus(), 5000);
    return () => clearInterval(interval);
  }, [autoRefresh, loadStatus]);

  if (status === "loading" || loading) {
    return (
      <AppShell userEmail={session?.user?.email}>
        <div className="flex items-center justify-center h-full min-h-[400px]">
          <Loader2 className="w-5 h-5 animate-spin text-gray-400 dark:text-zinc-600" />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell userEmail={session?.user?.email}>
      <div className="p-6 max-w-4xl">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-xl font-bold text-gray-900 dark:text-zinc-100">Build Queue</h1>
            <p className="text-xs text-gray-500 dark:text-zinc-500 mt-0.5">
              Redis-backed FIFO queue for GitOps writes
            </p>
          </div>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 cursor-pointer">
              <div className="relative">
                <input
                  type="checkbox"
                  checked={autoRefresh}
                  onChange={(e) => setAutoRefresh(e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-8 h-4 rounded-full bg-gray-100 dark:bg-zinc-800 peer-checked:bg-emerald-600 transition-colors" />
                <div className="absolute top-0.5 left-0.5 w-3 h-3 rounded-full bg-white shadow transition-transform peer-checked:translate-x-4" />
              </div>
              <span className="text-xs text-gray-500 dark:text-zinc-500">Auto (5s)</span>
            </label>
            <button
              onClick={() => void loadStatus()}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-200 dark:border-zinc-800 hover:border-gray-400 dark:hover:border-zinc-700 text-gray-500 dark:text-zinc-400 hover:text-gray-900 dark:hover:text-zinc-200 text-xs font-medium transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Refresh
            </button>
          </div>
        </div>

        {queueStatus === null ? (
          <div className="bg-white dark:bg-zinc-900/50 border border-gray-200 dark:border-zinc-800 rounded-xl p-8 text-center shadow-sm">
            <AlertTriangle className="w-8 h-8 text-amber-500 mx-auto mb-2" />
            <p className="text-sm font-medium text-gray-700 dark:text-zinc-300">Queue service unavailable</p>
            <p className="text-xs text-gray-400 dark:text-zinc-500 mt-1 max-w-md mx-auto">
              {errorMsg || "Ensure the Redis queue worker is running and the platform API is accessible."}
            </p>
            <button
              onClick={() => void loadStatus()}
              className="mt-4 inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Retry
            </button>
          </div>
        ) : (
          <>
            {/* Worker health */}
            <div className="mb-6 flex items-center gap-3 px-4 py-3 rounded-xl border border-gray-200 dark:border-zinc-800 bg-white dark:bg-zinc-900/50 shadow-sm">
              <Server className="w-4 h-4 text-gray-500 dark:text-zinc-500" />
              <span className="text-sm text-gray-500 dark:text-zinc-400">Worker</span>
              <div className="flex items-center gap-2">
                {queueStatus.worker_alive ? (
                  <>
                    <div className="w-2 h-2 rounded-full bg-emerald-500" />
                    <span className="text-sm font-medium text-emerald-400">Alive</span>
                  </>
                ) : (
                  <>
                    <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                    <span className="text-sm font-medium text-red-400">Dead</span>
                    <span className="text-xs text-gray-400 dark:text-zinc-600">— git writes will not be processed</span>
                  </>
                )}
              </div>
              <div className="ml-auto text-xs text-gray-400 dark:text-zinc-600">
                Last refreshed: {lastRefreshed.toLocaleTimeString()}
              </div>
            </div>

            {/* Queue metrics */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
              <div className="bg-white dark:bg-zinc-900/50 border border-gray-200 dark:border-zinc-800 rounded-xl px-4 py-4 shadow-sm">
                <div className="flex items-center gap-2 mb-3">
                  <Clock className="w-3.5 h-3.5 text-amber-500" />
                  <span className="text-xs font-medium text-gray-500 dark:text-zinc-500">Pending</span>
                </div>
                <p className="text-3xl font-bold text-gray-900 dark:text-zinc-100 font-mono">{queueStatus.pending}</p>
                {queueStatus.oldest_pending_age_seconds !== null && queueStatus.pending > 0 && (
                  <p className="text-xs text-gray-400 dark:text-zinc-600 mt-1">
                    Oldest: {Math.round(queueStatus.oldest_pending_age_seconds)}s ago
                  </p>
                )}
              </div>
              <div className="bg-white dark:bg-zinc-900/50 border border-gray-200 dark:border-zinc-800 rounded-xl px-4 py-4 shadow-sm">
                <div className="flex items-center gap-2 mb-3">
                  <Zap className={`w-3.5 h-3.5 ${queueStatus.processing > 0 ? "text-blue-500" : "text-gray-400 dark:text-zinc-600"}`} />
                  <span className="text-xs font-medium text-gray-500 dark:text-zinc-500">Processing</span>
                </div>
                <p className={`text-3xl font-bold font-mono ${queueStatus.processing > 0 ? "text-blue-400" : "text-gray-900 dark:text-zinc-100"}`}>
                  {queueStatus.processing}
                </p>
                {queueStatus.processing > 0 && (
                  <div className="flex items-center gap-1 mt-1">
                    <div className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
                    <p className="text-xs text-blue-500">active</p>
                  </div>
                )}
              </div>
              <div className="bg-white dark:bg-zinc-900/50 border border-gray-200 dark:border-zinc-800 rounded-xl px-4 py-4 shadow-sm">
                <div className="flex items-center gap-2 mb-3">
                  <AlertTriangle className={`w-3.5 h-3.5 ${queueStatus.dead_letter > 0 ? "text-red-500" : "text-gray-400 dark:text-zinc-600"}`} />
                  <span className="text-xs font-medium text-gray-500 dark:text-zinc-500">Dead Letter</span>
                </div>
                <p className={`text-3xl font-bold font-mono ${queueStatus.dead_letter > 0 ? "text-red-400" : "text-gray-900 dark:text-zinc-100"}`}>
                  {queueStatus.dead_letter}
                </p>
                {queueStatus.dead_letter > 0 && (
                  <p className="text-xs text-red-500 mt-1">requires attention</p>
                )}
              </div>
            </div>

            {/* Status summary */}
            <div className="bg-white dark:bg-zinc-900/50 border border-gray-200 dark:border-zinc-800 rounded-xl p-5 shadow-sm">
              <div className="flex items-center gap-2 mb-4">
                <Activity className="w-4 h-4 text-gray-500 dark:text-zinc-500" />
                <h3 className="text-sm font-semibold text-gray-700 dark:text-zinc-300">Queue Health Summary</h3>
              </div>
              <div className="space-y-3">
                <div className="flex items-start gap-3">
                  {queueStatus.worker_alive ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 mt-0.5 shrink-0" />
                  ) : (
                    <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 shrink-0" />
                  )}
                  <div>
                    <p className="text-xs font-medium text-gray-700 dark:text-zinc-300">Git Writer Worker</p>
                    <p className="text-xs text-gray-400 dark:text-zinc-600">
                      {queueStatus.worker_alive
                        ? "Single-worker FIFO queue is operational. Concurrent git conflicts prevented."
                        : "Worker is not running. Start it with: python -m app.workers.git_writer"}
                    </p>
                  </div>
                </div>
                {queueStatus.pending > 5 && (
                  <div className="flex items-start gap-3">
                    <AlertTriangle className="w-4 h-4 text-amber-500 mt-0.5 shrink-0" />
                    <div>
                      <p className="text-xs font-medium text-gray-700 dark:text-zinc-300">High Queue Depth</p>
                      <p className="text-xs text-gray-400 dark:text-zinc-600">
                        {queueStatus.pending} jobs pending. Consider checking worker performance or scaling.
                      </p>
                    </div>
                  </div>
                )}
                {queueStatus.dead_letter > 0 && (
                  <div className="flex items-start gap-3">
                    <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 shrink-0" />
                    <div>
                      <p className="text-xs font-medium text-gray-700 dark:text-zinc-300">Dead Letter Queue Has Items</p>
                      <p className="text-xs text-gray-400 dark:text-zinc-600">
                        {queueStatus.dead_letter} job(s) failed after 3 retries. Check API logs for details.
                        Jobs in DLQ: <span className="font-mono">haven:git:dlq</span>
                      </p>
                    </div>
                  </div>
                )}
                {queueStatus.pending === 0 && queueStatus.processing === 0 && queueStatus.dead_letter === 0 && queueStatus.worker_alive && (
                  <div className="flex items-start gap-3">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 mt-0.5 shrink-0" />
                    <div>
                      <p className="text-xs font-medium text-gray-700 dark:text-zinc-300">All Clear</p>
                      <p className="text-xs text-gray-400 dark:text-zinc-600">Queue is empty and worker is healthy.</p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </AppShell>
  );
}
