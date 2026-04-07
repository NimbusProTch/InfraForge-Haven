"use client";

import { useState } from "react";
import { ServiceIcon } from "@/components/icons/ServiceIcons";
import { api, AppServiceEntry } from "@/lib/api";
import { DropdownMenu, DropdownItem, DropdownDivider } from "@/components/ui/dropdown-menu";
import { DisconnectConfirmDialog } from "@/components/DisconnectConfirmDialog";
import {
  Link2,
  Key,
  Plus,
  Loader2,
  AlertCircle,
  Clock,
  MoreHorizontal,
  Copy,
  Check,
} from "lucide-react";

interface ConnectedServicesPanelProps {
  tenantSlug: string;
  appSlug: string;
  services: AppServiceEntry[];
  accessToken?: string;
  onRefresh: () => void;
  onAddService?: () => void;
}

export function ConnectedServicesPanel({
  tenantSlug,
  appSlug,
  services,
  accessToken,
  onRefresh,
  onAddService,
}: ConnectedServicesPanelProps) {
  const [showCredentials, setShowCredentials] = useState<string | null>(null);
  const [credentials, setCredentials] = useState<Record<string, string> | null>(null);
  const [credentialsLoading, setCredentialsLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [disconnectTarget, setDisconnectTarget] = useState<AppServiceEntry | null>(null);

  const connected = services.filter((s) => s.connected);
  const pending = services.filter((s) => s.pending);

  async function handleDisconnect() {
    if (!disconnectTarget) return;
    await api.services.disconnectFromApp(tenantSlug, appSlug, disconnectTarget.service_name, accessToken);
    onRefresh();
  }

  async function handleShowCredentials(serviceName: string) {
    if (showCredentials === serviceName) {
      setShowCredentials(null);
      setCredentials(null);
      return;
    }
    setCredentialsLoading(true);
    try {
      const data = await api.services.credentials(tenantSlug, serviceName, accessToken);
      setCredentials(data.credentials);
      setShowCredentials(serviceName);
    } catch (err) {
      console.error("Failed to fetch credentials:", err);
    } finally {
      setCredentialsLoading(false);
    }
  }

  function handleCopyConnection(hint: string) {
    navigator.clipboard.writeText(hint);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (services.length === 0) return null;

  const statusColor = (status: string) => {
    switch (status) {
      case "ready": return "bg-emerald-500";
      case "provisioning": case "updating": return "bg-amber-500 animate-pulse";
      case "failed": case "degraded": return "bg-red-500";
      default: return "bg-gray-400";
    }
  };

  return (
    <>
      <div className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-xl p-5 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <Link2 className="w-4 h-4 text-blue-500" />
            Connected Services
          </h3>
          {onAddService && (
            <button
              onClick={onAddService}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-blue-50 text-blue-600 hover:bg-blue-100 dark:bg-blue-500/10 dark:text-blue-400 dark:hover:bg-blue-500/20 transition-colors"
            >
              <Plus className="w-3.5 h-3.5" /> Add Service
            </button>
          )}
        </div>

        <div className="space-y-3">
          {/* Connected services */}
          {connected.map((svc) => (
            <div
              key={svc.service_name}
              className="flex items-start gap-3 p-3.5 rounded-lg border border-gray-100 dark:border-[#1e1e1e] bg-gray-50/50 dark:bg-[#0a0a0a]"
            >
              <ServiceIcon type={svc.service_type as "postgres" | "mysql" | "mongodb" | "redis" | "rabbitmq"} size={28} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="font-medium text-sm text-gray-900 dark:text-white">{svc.service_name}</span>
                  <span className={`w-2 h-2 rounded-full ${statusColor(svc.status)}`} />
                  <span className="text-xs text-gray-400 dark:text-[#666] capitalize">{svc.status}</span>
                </div>
                <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-[#888]">
                  <span className="capitalize">{svc.service_type}</span>
                  <span>·</span>
                  <span>{svc.tier}</span>
                </div>
                {svc.connection_hint && (
                  <p className="text-xs font-mono text-gray-400 dark:text-[#555] mt-1 truncate">
                    {svc.database_url_key ? `${svc.database_url_key}: ` : ""}{svc.connection_hint}
                  </p>
                )}

                {/* Credentials expand */}
                {showCredentials === svc.service_name && credentials && (
                  <div className="mt-2 p-2.5 rounded-lg bg-gray-100 dark:bg-[#1a1a1a] space-y-1.5">
                    {Object.entries(credentials).map(([key, value]) => (
                      <div key={key} className="flex items-center gap-2 text-xs">
                        <span className="font-mono text-gray-500 dark:text-[#888] w-32 shrink-0">{key}</span>
                        <span className="font-mono text-gray-900 dark:text-white truncate">{value}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Safe dropdown menu instead of direct disconnect button */}
              <DropdownMenu
                trigger={
                  <button className="p-1.5 rounded-md text-gray-400 hover:text-gray-600 dark:hover:text-zinc-300 hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors">
                    <MoreHorizontal className="w-4 h-4" />
                  </button>
                }
              >
                <DropdownItem onClick={() => handleShowCredentials(svc.service_name)}>
                  {credentialsLoading && showCredentials === svc.service_name ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Key className="w-4 h-4" />
                  )}
                  {showCredentials === svc.service_name ? "Hide Credentials" : "View Credentials"}
                </DropdownItem>
                {svc.connection_hint && (
                  <DropdownItem onClick={() => handleCopyConnection(svc.connection_hint!)}>
                    {copied ? <Check className="w-4 h-4 text-emerald-500" /> : <Copy className="w-4 h-4" />}
                    Copy Connection String
                  </DropdownItem>
                )}
                <DropdownDivider />
                <DropdownItem variant="danger" onClick={() => setDisconnectTarget(svc)}>
                  <AlertCircle className="w-4 h-4" />
                  Disconnect Service...
                </DropdownItem>
              </DropdownMenu>
            </div>
          ))}

          {/* Pending services */}
          {pending.map((svc) => (
            <div
              key={svc.service_name}
              className="flex items-center gap-3 p-3 rounded-lg border border-amber-200/50 dark:border-amber-500/20 bg-amber-50/30 dark:bg-amber-500/5"
            >
              <ServiceIcon type={svc.service_type as "postgres" | "mysql" | "mongodb" | "redis" | "rabbitmq"} size={24} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm text-gray-900 dark:text-white">{svc.service_name}</span>
                  <Clock className="w-3.5 h-3.5 text-amber-500 animate-pulse" />
                  <span className="text-xs text-amber-600 dark:text-amber-400">Provisioning...</span>
                </div>
                <span className="text-xs text-gray-500 dark:text-[#888] capitalize">{svc.service_type} · {svc.tier}</span>
              </div>
              {svc.error_message && (
                <div className="flex items-center gap-1 text-xs text-red-500">
                  <AlertCircle className="w-3.5 h-3.5" />
                  <span className="truncate max-w-[200px]">{svc.error_message}</span>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Typed confirmation for disconnect */}
      <DisconnectConfirmDialog
        open={!!disconnectTarget}
        onClose={() => setDisconnectTarget(null)}
        onConfirm={handleDisconnect}
        serviceName={disconnectTarget?.service_name ?? ""}
        serviceType={disconnectTarget?.service_type ?? ""}
      />
    </>
  );
}
