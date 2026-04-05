"use client";

import { useState } from "react";
import { X, Loader2, Settings, AlertTriangle } from "lucide-react";
import { type ManagedService } from "@/lib/api";

interface ModifyServiceModalProps {
  open: boolean;
  onClose: () => void;
  onConfirm: (updates: {
    replicas?: number;
    storage?: string;
    cpu?: string;
    memory?: string;
    tier?: string;
  }) => void;
  loading: boolean;
  service: ManagedService;
}

const EVEREST_TYPES = ["postgres", "mysql", "mongodb"];

export function ModifyServiceModal({
  open,
  onClose,
  onConfirm,
  loading,
  service,
}: ModifyServiceModalProps) {
  const [replicas, setReplicas] = useState(1);
  const [storage, setStorage] = useState("5");
  const [cpu, setCpu] = useState("1");
  const [memory, setMemory] = useState("1");
  const [tier, setTier] = useState<string>(service.tier);
  const [showTierUpgrade, setShowTierUpgrade] = useState(false);

  if (!open) return null;

  const isEverest = EVEREST_TYPES.includes(service.service_type);
  const isRedis = service.service_type === "redis";
  const isRabbitMQ = service.service_type === "rabbitmq";
  const maxReplicas = isRedis ? 3 : 7;

  const handleConfirm = () => {
    const updates: Record<string, unknown> = {};
    if (replicas !== 1) updates.replicas = replicas;
    if (isEverest || isRabbitMQ) {
      if (storage !== "5") updates.storage = `${storage}Gi`;
    }
    if (isEverest) {
      if (cpu !== "1") updates.cpu = cpu;
      if (memory !== "1") updates.memory = `${memory}Gi`;
    }
    if (tier !== service.tier) updates.tier = tier;
    onConfirm(updates as { replicas?: number; storage?: string; cpu?: string; memory?: string; tier?: string });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl shadow-2xl w-full max-w-md mx-4" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center">
              <Settings className="w-4 h-4 text-blue-400" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-zinc-100">Modify Service</h3>
              <p className="text-xs text-zinc-500">{service.name} ({service.service_type})</p>
            </div>
          </div>
          <button onClick={onClose} className="text-zinc-600 hover:text-zinc-300 transition-colors p-1 rounded-lg hover:bg-zinc-800">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-4">
          {/* Tier selector */}
          <div>
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2">Tier</p>
            <div className="flex items-center gap-2">
              {["dev", "prod"].map((t) => (
                <button
                  key={t}
                  onClick={() => {
                    setTier(t);
                    if (t === "prod" && service.tier === "dev") setShowTierUpgrade(true);
                    else setShowTierUpgrade(false);
                  }}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    tier === t
                      ? t === "prod" ? "bg-amber-600 text-white" : "bg-blue-600 text-white"
                      : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700 border border-zinc-700"
                  }`}
                >
                  {t.toUpperCase()}
                </button>
              ))}
            </div>
            {showTierUpgrade && (
              <div className="mt-2 bg-amber-500/5 border border-amber-500/10 rounded-lg p-2.5">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
                  <div>
                    <p className="text-xs text-amber-300/80">
                      Upgrade to PROD: 3 replicas, larger storage, HA failover.
                    </p>
                    <p className="text-[10px] text-amber-300/60 mt-0.5">Requires service restart.</p>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Replicas */}
          <div>
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2">Replicas</p>
            <div className="flex items-center gap-2">
              {Array.from({ length: maxReplicas }, (_, i) => i + 1)
                .filter((n) => [1, 2, 3, 5, 7].includes(n) && n <= maxReplicas)
                .map((n) => (
                  <button
                    key={n}
                    onClick={() => setReplicas(n)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                      replicas === n
                        ? "bg-blue-600 text-white"
                        : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700 border border-zinc-700"
                    }`}
                  >
                    {n}
                  </button>
                ))}
            </div>
          </div>

          {/* Storage (Everest + RabbitMQ only) */}
          {(isEverest || isRabbitMQ) && (
            <div>
              <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1.5">Storage</p>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  min="1"
                  value={storage}
                  onChange={(e) => setStorage(e.target.value)}
                  className="w-20 px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-800 text-sm text-zinc-200 font-mono focus:outline-none focus:ring-1 focus:ring-blue-500/50"
                />
                <span className="text-xs text-zinc-500">Gi</span>
              </div>
              <p className="text-[10px] text-zinc-600 mt-1">Storage can only be increased.</p>
            </div>
          )}

          {/* CPU + Memory (Everest only) */}
          {isEverest && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1.5">CPU (cores)</p>
                <input
                  type="text"
                  value={cpu}
                  onChange={(e) => setCpu(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-800 text-sm text-zinc-200 font-mono focus:outline-none focus:ring-1 focus:ring-blue-500/50"
                />
              </div>
              <div>
                <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1.5">Memory (Gi)</p>
                <input
                  type="text"
                  value={memory}
                  onChange={(e) => setMemory(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-800 text-sm text-zinc-200 font-mono focus:outline-none focus:ring-1 focus:ring-blue-500/50"
                />
              </div>
            </div>
          )}

          {/* Warning */}
          <div className="bg-amber-500/5 border border-amber-500/10 rounded-lg p-2.5">
            <p className="text-xs text-amber-300/80">
              Changes may cause brief downtime during restart.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 py-4 border-t border-zinc-800">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg border border-zinc-700 text-zinc-400 hover:text-zinc-200 text-xs font-medium transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-xs font-medium transition-colors"
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Settings className="w-3.5 h-3.5" />}
            Save Changes
          </button>
        </div>
      </div>
    </div>
  );
}
