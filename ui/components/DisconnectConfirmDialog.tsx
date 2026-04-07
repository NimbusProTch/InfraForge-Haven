"use client";

import { useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";

interface DisconnectConfirmDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => Promise<void>;
  serviceName: string;
  serviceType: string;
}

export function DisconnectConfirmDialog({
  open,
  onClose,
  onConfirm,
  serviceName,
  serviceType,
}: DisconnectConfirmDialogProps) {
  const [confirmText, setConfirmText] = useState("");
  const [loading, setLoading] = useState(false);

  if (!open) return null;

  const isMatch = confirmText === serviceName;

  async function handleConfirm() {
    if (!isMatch) return;
    setLoading(true);
    try {
      await onConfirm();
      setConfirmText("");
      onClose();
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        className="bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-800 rounded-2xl shadow-2xl w-full max-w-md mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-6 py-5">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-full bg-red-100 dark:bg-red-500/10 flex items-center justify-center">
              <AlertTriangle className="w-5 h-5 text-red-500" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-gray-900 dark:text-white">
                Disconnect {serviceName}?
              </h3>
              <p className="text-xs text-gray-500 dark:text-zinc-500 capitalize">{serviceType}</p>
            </div>
          </div>

          <div className="space-y-3 mb-5">
            <p className="text-sm text-gray-600 dark:text-zinc-400">
              This will remove the <span className="font-mono text-xs bg-gray-100 dark:bg-zinc-800 px-1.5 py-0.5 rounded">DATABASE_URL</span> environment
              variable from your application. The database itself will <strong>not</strong> be deleted, but your app will lose access.
            </p>
            <p className="text-sm text-gray-600 dark:text-zinc-400">
              Your application will need to be redeployed after disconnecting.
            </p>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-gray-700 dark:text-zinc-300">
              Type <span className="font-mono text-red-500">{serviceName}</span> to confirm:
            </label>
            <input
              type="text"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder={serviceName}
              className="w-full px-3 py-2.5 rounded-lg border border-gray-300 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-sm font-mono text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-red-500/30 focus:border-red-500/50"
              autoFocus
            />
          </div>
        </div>

        <div className="flex items-center justify-end gap-2.5 px-6 py-4 border-t border-gray-200 dark:border-zinc-800">
          <button
            onClick={() => { setConfirmText(""); onClose(); }}
            className="px-4 py-2 rounded-lg border border-gray-300 dark:border-zinc-700 text-gray-600 dark:text-zinc-400 hover:text-gray-900 dark:hover:text-zinc-200 text-sm font-medium transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={!isMatch || loading}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-red-600 hover:bg-red-700 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors"
          >
            {loading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            Disconnect
          </button>
        </div>
      </div>
    </div>
  );
}
