"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { RotateCcw, Loader2, AlertTriangle } from "lucide-react";

interface RestartModalProps {
  open: boolean;
  onClose: () => void;
  tenantSlug: string;
  appSlug: string;
  replicas: number;
  namespace: string;
  accessToken?: string;
  onSuccess: () => void;
}

export function RestartModal({
  open,
  onClose,
  tenantSlug,
  appSlug,
  replicas,
  namespace,
  accessToken,
  onSuccess,
}: RestartModalProps) {
  const [restarting, setRestarting] = useState(false);
  const [error, setError] = useState("");

  async function handleRestart() {
    setRestarting(true);
    setError("");
    try {
      await api.apps.restart(tenantSlug, appSlug, accessToken);
      onSuccess();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Restart failed");
    } finally {
      setRestarting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <RotateCcw className="w-5 h-5 text-amber-500" /> Restart: {appSlug}
          </DialogTitle>
          <DialogDescription>Perform a rolling restart of all pods.</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 mt-2">
          <div className="p-4 rounded-lg bg-gray-50 dark:bg-[#0a0a0a] border border-gray-100 dark:border-[#1e1e1e]">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-lg bg-blue-100 dark:bg-blue-500/20 flex items-center justify-center">
                <span className="text-lg font-bold text-blue-600 dark:text-blue-400">{replicas}</span>
              </div>
              <div>
                <p className="text-sm font-medium text-gray-900 dark:text-white">
                  {replicas} pod{replicas !== 1 ? "s" : ""} running
                </p>
                <p className="text-xs text-gray-500 dark:text-[#888]">
                  in namespace <span className="font-mono">{namespace}</span>
                </p>
              </div>
            </div>

            <div className="flex items-start gap-2 p-3 rounded-md bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20">
              <AlertTriangle className="w-4 h-4 text-amber-500 mt-0.5 shrink-0" />
              <div className="text-xs text-amber-700 dark:text-amber-400">
                <p className="font-medium mb-0.5">Rolling restart</p>
                <p>
                  Pods will be restarted one at a time. {replicas > 1
                    ? "With multiple replicas, there will be zero downtime."
                    : "With a single replica, there may be brief downtime."}
                </p>
              </div>
            </div>
          </div>

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
              onClick={handleRestart}
              disabled={restarting}
              className="inline-flex items-center gap-2 px-5 py-2 rounded-lg bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white text-sm font-semibold transition-colors"
            >
              {restarting && <Loader2 className="w-4 h-4 animate-spin" />}
              <RotateCcw className="w-4 h-4" />
              Restart Pods
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
