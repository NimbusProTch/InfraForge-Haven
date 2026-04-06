"use client";

import { useState, useEffect } from "react";
import { api, SyncDiffEntry, SyncOptions } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  RefreshCw,
  Loader2,
  CheckCircle,
  AlertTriangle,
  XCircle,
  Clock,
  Trash2,
} from "lucide-react";

interface SyncModalProps {
  open: boolean;
  onClose: () => void;
  tenantSlug: string;
  appSlug: string;
  accessToken?: string;
  onSuccess: () => void;
}

export function SyncModal({
  open,
  onClose,
  tenantSlug,
  appSlug,
  accessToken,
  onSuccess,
}: SyncModalProps) {
  const [health, setHealth] = useState("Unknown");
  const [syncStatus, setSyncStatus] = useState("Unknown");
  const [diffs, setDiffs] = useState<SyncDiffEntry[]>([]);
  const [history, setHistory] = useState<Array<Record<string, unknown>>>([]);
  const [loadingStatus, setLoadingStatus] = useState(false);
  const [loadingDiff, setLoadingDiff] = useState(false);

  // Options
  const [prune, setPrune] = useState(true);
  const [force, setForce] = useState(false);
  const [dryRun, setDryRun] = useState(false);

  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState("");
  const [syncResult, setSyncResult] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    loadData();
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  async function loadData() {
    setLoadingStatus(true);
    setLoadingDiff(true);
    try {
      const [status, diff, hist] = await Promise.all([
        api.deployments.syncStatus(tenantSlug, appSlug, accessToken),
        api.deployments.syncDiff(tenantSlug, appSlug, accessToken),
        api.deployments.deployHistory(tenantSlug, appSlug, accessToken),
      ]);
      setHealth(status.health || "Unknown");
      setSyncStatus(status.sync || "Unknown");
      setDiffs(diff);
      setHistory(hist.slice(0, 5));
    } catch {
      // Silently handle — status may be unavailable
    } finally {
      setLoadingStatus(false);
      setLoadingDiff(false);
    }
  }

  async function handleSync() {
    setSyncing(true);
    setError("");
    setSyncResult(null);
    try {
      const options: SyncOptions = { prune, force, dry_run: dryRun };
      const result = await api.deployments.syncWithOptions(tenantSlug, appSlug, options, accessToken);
      setSyncResult(result.triggered ? (dryRun ? "Dry run completed" : "Sync triggered successfully") : "Sync failed to trigger");
      if (result.triggered && !dryRun) {
        setTimeout(() => {
          onSuccess();
          onClose();
        }, 1500);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  }

  const healthIcon = health === "Healthy"
    ? <CheckCircle className="w-4 h-4 text-emerald-500" />
    : health === "Degraded"
      ? <XCircle className="w-4 h-4 text-red-500" />
      : <AlertTriangle className="w-4 h-4 text-amber-500" />;

  const syncIcon = syncStatus === "Synced"
    ? <CheckCircle className="w-4 h-4 text-emerald-500" />
    : syncStatus === "OutOfSync"
      ? <AlertTriangle className="w-4 h-4 text-amber-500" />
      : <Clock className="w-4 h-4 text-gray-400" />;

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-lg max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <RefreshCw className="w-5 h-5 text-blue-500" /> ArgoCD Sync: {appSlug}
          </DialogTitle>
          <DialogDescription>Review changes and sync with the cluster.</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 mt-2">
          {/* Current state */}
          <div className="flex items-center gap-4 p-3 rounded-lg bg-gray-50 dark:bg-[#0a0a0a] border border-gray-100 dark:border-[#1e1e1e]">
            {loadingStatus ? (
              <Loader2 className="w-4 h-4 animate-spin text-gray-400" />
            ) : (
              <>
                <div className="flex items-center gap-1.5">
                  {healthIcon}
                  <span className="text-sm font-medium text-gray-900 dark:text-white">{health}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  {syncIcon}
                  <span className="text-sm font-medium text-gray-900 dark:text-white">{syncStatus}</span>
                </div>
              </>
            )}
          </div>

          {/* Resource diff */}
          <div>
            <h3 className="text-sm font-semibold text-gray-700 dark:text-[#ccc] mb-2">What Will Change</h3>
            {loadingDiff ? (
              <div className="flex items-center gap-2 text-sm text-gray-400 py-3">
                <Loader2 className="w-4 h-4 animate-spin" /> Loading diff...
              </div>
            ) : diffs.length === 0 ? (
              <p className="text-sm text-gray-400 dark:text-[#666] py-2">All resources are in sync — no changes needed.</p>
            ) : (
              <div className="space-y-1.5 max-h-48 overflow-y-auto">
                {diffs.map((d, i) => (
                  <div key={i} className="flex items-center gap-2 p-2 rounded-md bg-white dark:bg-[#141414] border border-gray-100 dark:border-[#1e1e1e] text-xs">
                    <span className={`w-2 h-2 rounded-full shrink-0 ${
                      d.sync_status === "OutOfSync" ? "bg-amber-500" : d.health_status === "Degraded" ? "bg-red-500" : "bg-gray-400"
                    }`} />
                    <span className="font-mono text-gray-900 dark:text-white">{d.kind}/{d.name}</span>
                    <span className="text-gray-400">{d.sync_status}</span>
                    {d.requires_pruning && <Trash2 className="w-3 h-3 text-red-400" />}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Options */}
          <div>
            <h3 className="text-sm font-semibold text-gray-700 dark:text-[#ccc] mb-2">Sync Options</h3>
            <div className="space-y-2">
              {[
                { label: "Prune removed resources", checked: prune, onChange: setPrune },
                { label: "Force (override immutable fields)", checked: force, onChange: setForce },
                { label: "Dry Run (preview only)", checked: dryRun, onChange: setDryRun },
              ].map((opt) => (
                <label key={opt.label} className="flex items-center gap-2 text-sm cursor-pointer">
                  <input
                    type="checkbox"
                    checked={opt.checked}
                    onChange={(e) => opt.onChange(e.target.checked)}
                    className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span className="text-gray-700 dark:text-[#ccc]">{opt.label}</span>
                </label>
              ))}
            </div>
          </div>

          {/* History */}
          {history.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-gray-700 dark:text-[#ccc] mb-2">Recent Syncs</h3>
              <div className="space-y-1">
                {history.map((h, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs text-gray-500 dark:text-[#888]">
                    <CheckCircle className="w-3 h-3 text-emerald-500" />
                    <span className="font-mono">{String(h.revision || "").slice(0, 7)}</span>
                    <span>{h.deployedAt ? new Date(h.deployedAt as string).toLocaleString() : ""}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Result / Error */}
          {syncResult && (
            <p className="text-sm text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/20 rounded-lg px-3 py-2">
              {syncResult}
            </p>
          )}
          {error && (
            <p className="text-sm text-red-500 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <button onClick={onClose} className="px-4 py-2 text-sm text-gray-600 dark:text-[#999] hover:text-gray-900 transition-colors">
              Cancel
            </button>
            <button
              onClick={handleSync}
              disabled={syncing}
              className="inline-flex items-center gap-2 px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-semibold transition-colors"
            >
              {syncing && <Loader2 className="w-4 h-4 animate-spin" />}
              <RefreshCw className="w-4 h-4" />
              {dryRun ? "Dry Run" : "Sync Now"}
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
