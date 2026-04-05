"use client";

import { useEffect, useState, useCallback } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, type BackupItem } from "@/lib/api";
import {
  Loader2,
  RotateCcw,
  Download,
  Clock,
  AlertCircle,
  Database,
  Calendar,
  X,
} from "lucide-react";

interface BackupPanelProps {
  tenantSlug: string;
  serviceName: string;
  serviceType: string;
  accessToken?: string;
}

const STATUS_VARIANT: Record<string, "success" | "warning" | "destructive" | "secondary"> = {
  completed: "success",
  in_progress: "warning",
  pending: "secondary",
  failed: "destructive",
};

export function BackupPanel({ tenantSlug, serviceName, serviceType, accessToken }: BackupPanelProps) {
  const [backups, setBackups] = useState<BackupItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [triggering, setTriggering] = useState(false);
  const [restoreDialog, setRestoreDialog] = useState<BackupItem | null>(null);
  const [restoring, setRestoring] = useState(false);
  const [pitrTime, setPitrTime] = useState("");

  const fetchBackups = useCallback(async () => {
    try {
      const data = await api.backups.list(tenantSlug, serviceName, accessToken);
      setBackups(Array.isArray(data) ? data : []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load backups");
    } finally {
      setLoading(false);
    }
  }, [tenantSlug, serviceName, accessToken]);

  useEffect(() => {
    fetchBackups();
  }, [fetchBackups]);

  // Auto-refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(fetchBackups, 30000);
    return () => clearInterval(interval);
  }, [fetchBackups]);

  async function handleTriggerBackup() {
    setTriggering(true);
    try {
      await api.backups.trigger(tenantSlug, serviceName, accessToken);
      // Refresh list after a short delay to let the backup start
      setTimeout(fetchBackups, 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to trigger backup");
    } finally {
      setTriggering(false);
    }
  }

  async function handleRestore(backup: BackupItem) {
    setRestoring(true);
    try {
      const body = serviceType === "postgres" && pitrTime ? { target_time: pitrTime } : undefined;
      await api.backups.restore(tenantSlug, serviceName, backup.id, body, accessToken);
      setRestoreDialog(null);
      setPitrTime("");
      setTimeout(fetchBackups, 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to restore backup");
    } finally {
      setRestoring(false);
    }
  }

  function formatDate(dateStr: string) {
    return new Date(dateStr).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function formatSize(bytes: number | null) {
    if (bytes === null || bytes === undefined) return "--";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-6">
        <Loader2 className="w-4 h-4 animate-spin text-gray-400 dark:text-zinc-600 mr-2" />
        <span className="text-xs text-gray-500 dark:text-zinc-500">Loading backups...</span>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Header with actions */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <RotateCcw className="w-3.5 h-3.5 text-gray-400 dark:text-zinc-500" />
          <span className="text-xs font-medium text-gray-600 dark:text-zinc-400 uppercase tracking-wider">
            Backups
          </span>
          <span className="text-xs text-gray-400 dark:text-zinc-600">
            (auto-refresh 30s)
          </span>
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={handleTriggerBackup}
          disabled={triggering}
          className="h-7 text-xs"
        >
          {triggering ? (
            <Loader2 className="w-3 h-3 animate-spin mr-1" />
          ) : (
            <Download className="w-3 h-3 mr-1" />
          )}
          Take Snapshot
        </Button>
      </div>

      {/* Error state */}
      {error && (
        <div className="flex items-center gap-2 p-2.5 rounded-lg bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900/50">
          <AlertCircle className="w-3.5 h-3.5 text-red-500 shrink-0" />
          <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
        </div>
      )}

      {/* Empty state */}
      {backups.length === 0 && !error ? (
        <div className="text-center py-6 border border-dashed border-gray-200 dark:border-zinc-800 rounded-lg">
          <Database className="w-6 h-6 mx-auto mb-1.5 text-gray-300 dark:text-zinc-700" />
          <p className="text-xs text-gray-500 dark:text-zinc-500">No backups yet.</p>
          <p className="text-xs text-gray-400 dark:text-zinc-600 mt-0.5">
            Take a snapshot or enable scheduled backups.
          </p>
        </div>
      ) : (
        /* Backup table */
        <div className="border border-gray-200 dark:border-zinc-800 rounded-lg overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-gray-50 dark:bg-zinc-800/60 border-b border-gray-200 dark:border-zinc-800">
                <th className="text-left font-medium text-gray-500 dark:text-zinc-500 px-3 py-2">
                  Name
                </th>
                <th className="text-left font-medium text-gray-500 dark:text-zinc-500 px-3 py-2">
                  Status
                </th>
                <th className="text-left font-medium text-gray-500 dark:text-zinc-500 px-3 py-2">
                  Date
                </th>
                <th className="text-left font-medium text-gray-500 dark:text-zinc-500 px-3 py-2">
                  Size
                </th>
                <th className="text-right font-medium text-gray-500 dark:text-zinc-500 px-3 py-2">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-zinc-800/50">
              {backups.map((backup) => (
                <tr
                  key={backup.id}
                  className="hover:bg-gray-50/50 dark:hover:bg-zinc-800/30 transition-colors"
                >
                  <td className="px-3 py-2 font-mono text-gray-700 dark:text-zinc-300 truncate max-w-[140px]">
                    {backup.id.slice(0, 12)}
                  </td>
                  <td className="px-3 py-2">
                    <Badge
                      variant={STATUS_VARIANT[backup.status] ?? "secondary"}
                    >
                      {backup.status.replace("_", " ")}
                    </Badge>
                  </td>
                  <td className="px-3 py-2 text-gray-500 dark:text-zinc-500">
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {formatDate(backup.created_at)}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-gray-500 dark:text-zinc-500">
                    {formatSize(backup.size_bytes)}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {backup.status === "completed" && (
                      <button
                        onClick={() => {
                          setRestoreDialog(backup);
                          setPitrTime("");
                        }}
                        className="text-xs text-blue-500 hover:text-blue-600 dark:text-blue-400 dark:hover:text-blue-300 font-medium transition-colors"
                      >
                        Restore
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Restore confirmation dialog */}
      {restoreDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
          <div className="bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-800 rounded-xl w-full max-w-md mx-4 shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-zinc-800">
              <div className="flex items-center gap-2">
                <RotateCcw className="w-4 h-4 text-amber-500" />
                <h3 className="text-sm font-semibold text-gray-900 dark:text-zinc-100">
                  Restore Backup
                </h3>
              </div>
              <button
                onClick={() => setRestoreDialog(null)}
                className="text-gray-400 dark:text-zinc-600 hover:text-gray-700 dark:hover:text-zinc-300 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-5 space-y-4">
              <div className="p-3 rounded-lg bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/50">
                <p className="text-xs text-amber-700 dark:text-amber-400">
                  This will restore <span className="font-mono font-semibold">{serviceName}</span> to
                  the state captured in backup <span className="font-mono">{restoreDialog.id.slice(0, 12)}</span>
                  {" "}from {formatDate(restoreDialog.created_at)}. Current data will be overwritten.
                </p>
              </div>

              {/* PITR timestamp picker (postgres only) */}
              {serviceType === "postgres" && (
                <div className="space-y-1.5">
                  <label className="flex items-center gap-1.5 text-xs font-medium text-gray-600 dark:text-zinc-400">
                    <Calendar className="w-3 h-3" />
                    Point-in-time recovery (optional)
                  </label>
                  <input
                    type="datetime-local"
                    value={pitrTime}
                    onChange={(e) => setPitrTime(e.target.value)}
                    className="w-full rounded-lg border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 px-3 py-2 text-xs text-gray-700 dark:text-zinc-300 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <p className="text-xs text-gray-400 dark:text-zinc-600">
                    Leave empty to restore the full backup snapshot.
                  </p>
                </div>
              )}

              <div className="flex justify-end gap-2 pt-1">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setRestoreDialog(null)}
                >
                  Cancel
                </Button>
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={() => handleRestore(restoreDialog)}
                  disabled={restoring}
                >
                  {restoring ? (
                    <>
                      <Loader2 className="w-3 h-3 animate-spin mr-1" />
                      Restoring...
                    </>
                  ) : (
                    "Confirm Restore"
                  )}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
