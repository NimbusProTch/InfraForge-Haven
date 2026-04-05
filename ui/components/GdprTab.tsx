"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { Badge } from "@/components/ui/badge";
import {
  Loader2,
  Shield,
  Download,
  Trash2,
  Clock,
  CheckCircle2,
  AlertTriangle,
  X,
} from "lucide-react";

interface Consent {
  id: string;
  consent_type: string;
  granted_at: string;
  withdrawn_at: string | null;
}

interface RetentionPolicy {
  audit_log_days: number;
  deployment_log_days: number;
  build_log_days: number;
  usage_record_days: number;
  inactive_app_days: number;
}

interface GdprTabProps {
  tenantSlug: string;
  accessToken?: string;
}

export default function GdprTab({ tenantSlug, accessToken }: GdprTabProps) {
  const { error: toastError, success: toastSuccess } = useToast();
  const [consents, setConsents] = useState<Consent[]>([]);
  const [retention, setRetention] = useState<RetentionPolicy | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [showErase, setShowErase] = useState(false);
  const [eraseConfirm, setEraseConfirm] = useState("");
  const [erasing, setErasing] = useState(false);
  const [savingRetention, setSavingRetention] = useState(false);
  const [auditDays, setAuditDays] = useState(90);
  const [deployDays, setDeployDays] = useState(90);
  const [buildDays, setBuildDays] = useState(30);

  const loadData = useCallback(async () => {
    try {
      const [c, r] = await Promise.all([
        api.gdpr.listConsents(tenantSlug, accessToken),
        api.gdpr.getRetention(tenantSlug, accessToken),
      ]);
      setConsents(c as unknown as Consent[]);
      const rp = r as unknown as RetentionPolicy;
      setRetention(rp);
      if (rp) {
        setAuditDays(rp.audit_log_days);
        setDeployDays(rp.deployment_log_days);
        setBuildDays(rp.build_log_days);
      }
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [tenantSlug, accessToken]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  async function exportData() {
    setExporting(true);
    try {
      const data = await api.gdpr.export(tenantSlug, accessToken);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${tenantSlug}-data-export.json`;
      a.click();
      URL.revokeObjectURL(url);
      toastSuccess("Data exported successfully");
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  async function eraseData() {
    setErasing(true);
    try {
      await api.gdpr.erase(tenantSlug, { confirmation: "ERASE MY DATA" }, accessToken);
      toastSuccess("All data has been erased");
      window.location.href = "/tenants";
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Erasure failed");
    } finally {
      setErasing(false);
    }
  }

  async function updateRetention() {
    setSavingRetention(true);
    try {
      await api.gdpr.updateRetention(tenantSlug, { audit_log_days: auditDays, deployment_log_days: deployDays, build_log_days: buildDays }, accessToken);
      toastSuccess("Retention policy updated");
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Failed to update");
    } finally {
      setSavingRetention(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-5 h-5 animate-spin text-gray-400 dark:text-zinc-600" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <p className="text-sm text-gray-500 dark:text-zinc-500">GDPR / AVG compliance controls for data portability, erasure, and retention.</p>

      {/* Data Export (Article 20) */}
      <div className="bg-white dark:bg-zinc-900/50 border border-gray-200 dark:border-zinc-800 rounded-xl p-5 shadow-sm">
        <div className="flex items-center gap-3 mb-3">
          <Download className="w-5 h-5 text-blue-500" />
          <div>
            <h3 className="text-sm font-medium text-gray-800 dark:text-zinc-200">Data Export</h3>
            <p className="text-xs text-gray-400 dark:text-zinc-600">Article 20 — Right to data portability</p>
          </div>
        </div>
        <p className="text-xs text-gray-500 dark:text-zinc-500 mb-3">Download all tenant data including applications, deployments, members, and configurations.</p>
        <button
          onClick={exportData}
          disabled={exporting}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium transition-colors disabled:opacity-50"
        >
          {exporting ? <Loader2 className="w-3 h-3 animate-spin" /> : <Download className="w-3 h-3" />}
          Export All Data
        </button>
      </div>

      {/* Retention Policy */}
      <div className="bg-white dark:bg-zinc-900/50 border border-gray-200 dark:border-zinc-800 rounded-xl p-5 shadow-sm">
        <div className="flex items-center gap-3 mb-3">
          <Clock className="w-5 h-5 text-amber-500" />
          <div>
            <h3 className="text-sm font-medium text-gray-800 dark:text-zinc-200">Data Retention</h3>
            <p className="text-xs text-gray-400 dark:text-zinc-600">Configure how long data is retained</p>
          </div>
        </div>
        <div className="space-y-3">
          {[
            { label: "Audit logs", value: auditDays, setter: setAuditDays },
            { label: "Deployment logs", value: deployDays, setter: setDeployDays },
            { label: "Build logs", value: buildDays, setter: setBuildDays },
          ].map(({ label, value, setter }) => (
            <div key={label}>
              <label className="block text-xs font-medium text-gray-500 dark:text-zinc-400 mb-1.5">
                {label}: <span className="text-gray-800 dark:text-zinc-200">{value} days</span>
              </label>
              <input
                type="range"
                min={7}
                max={365}
                step={7}
                value={value}
                onChange={(e) => setter(Number(e.target.value))}
                className="w-full h-1.5 bg-gray-300 dark:bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-amber-500"
              />
            </div>
          ))}
          <button
            onClick={updateRetention}
            disabled={savingRetention}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-100 dark:bg-zinc-800 hover:bg-gray-200 dark:hover:bg-zinc-700 text-xs font-medium text-gray-700 dark:text-zinc-300 transition-colors disabled:opacity-50"
          >
            {savingRetention ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle2 className="w-3 h-3" />}
            Save Policy
          </button>
        </div>
      </div>

      {/* Consents */}
      {consents.length > 0 && (
        <div className="bg-white dark:bg-zinc-900/50 border border-gray-200 dark:border-zinc-800 rounded-xl p-5 shadow-sm">
          <h3 className="text-sm font-medium text-gray-800 dark:text-zinc-200 mb-3">Active Consents</h3>
          <div className="space-y-2">
            {consents.map((c) => (
              <div key={c.id} className="flex items-center justify-between py-2 border-b border-gray-200 dark:border-zinc-800/50 last:border-0">
                <div>
                  <p className="text-xs font-medium text-gray-700 dark:text-zinc-300">{c.consent_type}</p>
                  <p className="text-xs text-gray-400 dark:text-zinc-600">Granted {new Date(c.granted_at).toLocaleDateString()}</p>
                </div>
                <Badge variant={c.withdrawn_at ? "destructive" : "success"}>
                  {c.withdrawn_at ? "Withdrawn" : "Active"}
                </Badge>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Data Erasure (Article 17) */}
      <div className="bg-red-950/20 border border-red-900/30 rounded-xl p-5">
        <div className="flex items-center gap-3 mb-3">
          <AlertTriangle className="w-5 h-5 text-red-500" />
          <div>
            <h3 className="text-sm font-medium text-red-400">Right to Erasure</h3>
            <p className="text-xs text-gray-400 dark:text-zinc-600">Article 17 — Permanently delete all data</p>
          </div>
        </div>
        <p className="text-xs text-gray-500 dark:text-zinc-500 mb-3">
          This will permanently delete the tenant, all applications, services, deployments, and member data. This action cannot be undone.
        </p>
        <button
          onClick={() => setShowErase(true)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-600/20 hover:bg-red-600/30 border border-red-600/30 text-red-400 text-xs font-medium transition-colors"
        >
          <Trash2 className="w-3 h-3" />
          Request Data Erasure
        </button>
      </div>

      {/* Erasure confirmation modal */}
      {showErase && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
          <div className="bg-white dark:bg-zinc-900 border border-red-900/50 rounded-xl w-full max-w-md mx-4 shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-zinc-800">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-red-500" />
                <h2 className="text-sm font-semibold text-red-400">Confirm Data Erasure</h2>
              </div>
              <button onClick={() => setShowErase(false)} className="text-gray-400 dark:text-zinc-600 hover:text-gray-700 dark:hover:text-zinc-300 transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <p className="text-xs text-gray-500 dark:text-zinc-500">
                Type <span className="font-mono font-medium text-red-400">ERASE MY DATA</span> to confirm permanent deletion.
              </p>
              <input
                type="text"
                value={eraseConfirm}
                onChange={(e) => setEraseConfirm(e.target.value)}
                placeholder="ERASE MY DATA"
                className="w-full px-3 py-2 rounded-lg border border-red-900/50 bg-gray-100 dark:bg-zinc-800 text-sm text-gray-900 dark:text-zinc-100 placeholder:text-gray-400 dark:placeholder:text-zinc-600 focus:outline-none focus:border-red-600 focus:ring-1 focus:ring-red-600/30 font-mono"
                autoFocus
              />
              <div className="flex justify-end gap-2">
                <button onClick={() => { setShowErase(false); setEraseConfirm(""); }} className="px-3 py-1.5 rounded-lg text-xs font-medium text-gray-500 dark:text-zinc-500 hover:text-gray-800 dark:hover:text-zinc-200 hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors">
                  Cancel
                </button>
                <button
                  onClick={eraseData}
                  disabled={eraseConfirm !== "ERASE MY DATA" || erasing}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-700 text-white text-xs font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {erasing && <Loader2 className="w-3 h-3 animate-spin" />}
                  Erase All Data
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
