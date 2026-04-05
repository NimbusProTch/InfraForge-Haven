"use client";

import { useEffect, useState, useCallback } from "react";
import { api, type Domain } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { Badge } from "@/components/ui/badge";
import {
  Plus,
  Loader2,
  Globe,
  Trash2,
  X,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  Clock,
  Copy,
  Check,
  RefreshCw,
  ExternalLink,
} from "lucide-react";

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      className="text-gray-400 dark:text-zinc-600 hover:text-gray-700 dark:hover:text-gray-700 dark:text-zinc-300 transition-colors"
    >
      {copied ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
    </button>
  );
}

const CERT_STATUS_CONFIG: Record<string, { icon: typeof CheckCircle2; color: string; label: string }> = {
  issued: { icon: CheckCircle2, color: "text-emerald-500", label: "Active" },
  pending: { icon: Clock, color: "text-amber-500", label: "Pending" },
  failed: { icon: AlertCircle, color: "text-red-500", label: "Failed" },
};

interface DomainsTabProps {
  tenantSlug: string;
  appSlug: string;
  accessToken?: string;
}

export default function DomainsTab({ tenantSlug, appSlug, accessToken }: DomainsTabProps) {
  const { error: toastError, success: toastSuccess } = useToast();
  const [domains, setDomains] = useState<Domain[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [adding, setAdding] = useState(false);
  const [verifying, setVerifying] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [newDomain, setNewDomain] = useState("");

  const loadDomains = useCallback(async () => {
    try {
      const d = await api.domains.list(tenantSlug, appSlug, accessToken);
      setDomains(d);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [tenantSlug, appSlug, accessToken]);

  useEffect(() => {
    loadDomains();
  }, [loadDomains]);

  async function addDomain() {
    if (!newDomain.trim()) return;
    setAdding(true);
    try {
      const domain = await api.domains.add(tenantSlug, appSlug, { domain: newDomain.trim().toLowerCase() }, accessToken);
      setDomains((prev) => [...prev, domain]);
      toastSuccess(`Domain "${domain.domain}" added`);
      setShowAdd(false);
      setNewDomain("");
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Failed to add domain");
    } finally {
      setAdding(false);
    }
  }

  async function verifyDomain(domain: string) {
    setVerifying(domain);
    try {
      const result = await api.domains.verify(tenantSlug, appSlug, domain, accessToken);
      if (result.verified) {
        toastSuccess(`${domain} verified successfully!`);
        loadDomains();
      } else {
        toastError(`DNS verification failed for ${domain}. Check your TXT record.`);
      }
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Verification failed");
    } finally {
      setVerifying(null);
    }
  }

  async function deleteDomain(domain: string) {
    if (!confirm(`Remove domain "${domain}"?`)) return;
    setDeleting(domain);
    try {
      await api.domains.delete(tenantSlug, appSlug, domain, accessToken);
      setDomains((prev) => prev.filter((d) => d.domain !== domain));
      toastSuccess(`Domain "${domain}" removed`);
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Failed to remove domain");
    } finally {
      setDeleting(null);
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
    <div>
      <div className="flex items-center justify-between mb-5">
        <p className="text-sm text-gray-500 dark:text-zinc-500">Custom domains with automatic SSL via Let&apos;s Encrypt</p>
        <button
          onClick={() => setShowAdd(true)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium transition-colors"
        >
          <Plus className="w-3 h-3" />
          Add Domain
        </button>
      </div>

      {/* Add domain modal */}
      {showAdd && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
          <div className="bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-800 rounded-xl w-full max-w-md mx-4 shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-zinc-800">
              <div className="flex items-center gap-2">
                <Globe className="w-4 h-4 text-blue-500" />
                <h2 className="text-sm font-semibold text-gray-900 dark:text-zinc-100">Add Custom Domain</h2>
              </div>
              <button onClick={() => setShowAdd(false)} className="text-gray-400 dark:text-zinc-600 hover:text-gray-700 dark:hover:text-gray-700 dark:text-zinc-300 transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-5 space-y-4">
              <div>
                <label className="block text-xs font-medium text-gray-500 dark:text-zinc-400 mb-1.5">Domain</label>
                <input
                  type="text"
                  value={newDomain}
                  onChange={(e) => setNewDomain(e.target.value)}
                  placeholder="app.gemeente-utrecht.nl"
                  className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-zinc-700 bg-gray-100 dark:bg-zinc-800 text-sm text-gray-900 dark:text-zinc-100 placeholder:text-gray-400 dark:placeholder:text-zinc-600 focus:outline-none focus:border-blue-600 focus:ring-1 focus:ring-blue-600/30 font-mono"
                  autoFocus
                />
                <p className="text-xs text-gray-400 dark:text-zinc-600 mt-1">Enter the domain without http:// or https://</p>
              </div>

              {/* DNS instructions preview */}
              {newDomain.trim() && (
                <div className="bg-gray-50 dark:bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3">
                  <p className="text-xs font-medium text-gray-500 dark:text-zinc-400 mb-2">After adding, configure DNS:</p>
                  <div className="space-y-1.5">
                    <div className="flex items-center gap-2 text-xs">
                      <span className="text-gray-400 dark:text-zinc-600 w-12">Type</span>
                      <span className="font-mono text-gray-700 dark:text-zinc-300">CNAME</span>
                    </div>
                    <div className="flex items-center gap-2 text-xs">
                      <span className="text-gray-400 dark:text-zinc-600 w-12">Name</span>
                      <span className="font-mono text-gray-700 dark:text-zinc-300">{newDomain.trim()}</span>
                    </div>
                    <div className="flex items-center gap-2 text-xs">
                      <span className="text-gray-400 dark:text-zinc-600 w-12">Value</span>
                      <span className="font-mono text-emerald-400">{appSlug}.{tenantSlug}.apps.haven.nl</span>
                    </div>
                  </div>
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <button
                  onClick={() => setShowAdd(false)}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium text-gray-500 dark:text-zinc-500 hover:text-gray-900 dark:hover:text-gray-800 dark:text-zinc-200 hover:bg-gray-100 dark:hover:bg-gray-100 dark:bg-zinc-800 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={addDomain}
                  disabled={!newDomain.trim() || adding}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {adding && <Loader2 className="w-3 h-3 animate-spin" />}
                  Add Domain
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Domain list */}
      {domains.length === 0 ? (
        <div className="text-center py-16 border border-dashed border-gray-200 dark:border-zinc-800 rounded-xl">
          <Globe className="w-8 h-8 mx-auto mb-2 text-gray-400 dark:text-zinc-700" />
          <p className="text-sm text-gray-500 dark:text-zinc-500">No custom domains configured.</p>
          <p className="text-xs text-gray-400 dark:text-zinc-600 mt-1">Add a domain and point your DNS to enable HTTPS access.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {domains.map((d) => {
            const certCfg = CERT_STATUS_CONFIG[d.certificate_status ?? "pending"] ?? CERT_STATUS_CONFIG.pending;
            const CertIcon = certCfg.icon;

            return (
              <div
                key={d.domain}
                className="bg-white dark:bg-zinc-900/50 border border-gray-200 dark:border-zinc-800 rounded-xl shadow-sm p-4 hover:border-gray-400 dark:hover:border-gray-300 dark:border-zinc-700 transition-colors"
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${d.verified_at ? "bg-emerald-500/10" : "bg-amber-500/10"}`}>
                      {d.verified_at ? (
                        <ShieldCheck className="w-4 h-4 text-emerald-500" />
                      ) : (
                        <AlertCircle className="w-4 h-4 text-amber-500" />
                      )}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <a
                          href={`https://${d.domain}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sm font-medium text-gray-800 dark:text-zinc-200 hover:text-gray-900 dark:text-zinc-100 font-mono flex items-center gap-1"
                        >
                          {d.domain}
                          <ExternalLink className="w-3 h-3 text-gray-400 dark:text-zinc-600" />
                        </a>
                        <CopyButton text={d.domain} />
                      </div>
                      <div className="flex items-center gap-3 mt-1 text-xs">
                        <span className={`flex items-center gap-1 ${d.verified_at ? "text-emerald-500" : "text-amber-500"}`}>
                          {d.verified_at ? <CheckCircle2 className="w-3 h-3" /> : <Clock className="w-3 h-3" />}
                          {d.verified_at ? "DNS Verified" : "Pending Verification"}
                        </span>
                        <span className={`flex items-center gap-1 ${certCfg.color}`}>
                          <CertIcon className="w-3 h-3" />
                          SSL: {certCfg.label}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {!d.verified_at && (
                      <button
                        onClick={() => verifyDomain(d.domain)}
                        disabled={verifying === d.domain}
                        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-amber-600/10 hover:bg-amber-600/20 text-amber-400 text-xs font-medium transition-colors disabled:opacity-50"
                      >
                        {verifying === d.domain ? (
                          <Loader2 className="w-3 h-3 animate-spin" />
                        ) : (
                          <RefreshCw className="w-3 h-3" />
                        )}
                        Verify
                      </button>
                    )}
                    <button
                      onClick={() => deleteDomain(d.domain)}
                      disabled={deleting === d.domain}
                      className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium text-gray-400 dark:text-zinc-600 hover:text-red-400 hover:bg-red-950/30 transition-colors disabled:opacity-50"
                    >
                      {deleting === d.domain ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <Trash2 className="w-3 h-3" />
                      )}
                    </button>
                  </div>
                </div>

                {/* DNS instructions for unverified domains */}
                {!d.verified_at && d.verification_token && (
                  <div className="mt-3 bg-gray-50 dark:bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3">
                    <p className="text-xs font-medium text-gray-500 dark:text-zinc-400 mb-2">Add this DNS record to verify ownership:</p>
                    <div className="space-y-1.5">
                      <div className="flex items-center gap-2 text-xs">
                        <span className="text-gray-400 dark:text-zinc-600 w-12">Type</span>
                        <span className="font-mono text-gray-700 dark:text-zinc-300">TXT</span>
                      </div>
                      <div className="flex items-center gap-2 text-xs">
                        <span className="text-gray-400 dark:text-zinc-600 w-12">Name</span>
                        <span className="font-mono text-gray-700 dark:text-zinc-300">_haven-verify.{d.domain}</span>
                        <CopyButton text={`_haven-verify.${d.domain}`} />
                      </div>
                      <div className="flex items-center gap-2 text-xs">
                        <span className="text-gray-400 dark:text-zinc-600 w-12">Value</span>
                        <span className="font-mono text-emerald-400 truncate">{d.verification_token}</span>
                        <CopyButton text={d.verification_token} />
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
