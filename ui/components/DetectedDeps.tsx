"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import type { DetectedDeps as DetectedDepsType } from "@/lib/api";
import {
  Code2,
  Database,
  Layers,
  Loader2,
  Plus,
  Server,
  Zap,
} from "lucide-react";

interface DetectedDepsProps {
  deps: DetectedDepsType | null;
  loading?: boolean;
  onProvision?: (serviceType: string) => void;
}

const LANGUAGE_COLORS: Record<string, string> = {
  python: "bg-yellow-500/15 text-yellow-600 dark:text-yellow-400 border-yellow-500/30",
  "node.js": "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30",
  nodejs: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30",
  go: "bg-cyan-500/15 text-cyan-600 dark:text-cyan-400 border-cyan-500/30",
  ruby: "bg-red-500/15 text-red-600 dark:text-red-400 border-red-500/30",
  rust: "bg-orange-500/15 text-orange-600 dark:text-orange-400 border-orange-500/30",
  java: "bg-blue-500/15 text-blue-600 dark:text-blue-400 border-blue-500/30",
  php: "bg-indigo-500/15 text-indigo-600 dark:text-indigo-400 border-indigo-500/30",
};

const DB_ICONS: Record<string, { label: string; color: string }> = {
  postgresql: { label: "PostgreSQL", color: "text-blue-500" },
  postgres: { label: "PostgreSQL", color: "text-blue-500" },
  mysql: { label: "MySQL", color: "text-orange-500" },
  mongodb: { label: "MongoDB", color: "text-emerald-500" },
  sqlite: { label: "SQLite", color: "text-gray-500" },
};

const CACHE_ICONS: Record<string, { label: string; color: string }> = {
  redis: { label: "Redis", color: "text-red-500" },
  memcached: { label: "Memcached", color: "text-green-500" },
};

const QUEUE_ICONS: Record<string, { label: string; color: string }> = {
  rabbitmq: { label: "RabbitMQ", color: "text-orange-500" },
  kafka: { label: "Kafka", color: "text-gray-500" },
  celery: { label: "Celery", color: "text-emerald-500" },
};

export default function DetectedDeps({ deps, loading, onProvision }: DetectedDepsProps) {
  const [provisioning, setProvisioning] = useState<string | null>(null);

  if (loading) {
    return (
      <div className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg p-5">
        <div className="flex items-center gap-2 text-gray-400 dark:text-[#555]">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span className="text-sm">Analyzing repository dependencies...</span>
        </div>
      </div>
    );
  }

  if (!deps) {
    return (
      <div className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg p-5">
        <div className="text-center py-6">
          <Code2 className="w-8 h-8 mx-auto mb-2 text-gray-300 dark:text-[#333]" />
          <p className="text-sm text-gray-500 dark:text-[#666]">No dependency data available.</p>
          <p className="text-xs text-gray-400 dark:text-[#555] mt-1">
            Select a repository to auto-detect dependencies.
          </p>
        </div>
      </div>
    );
  }

  const hasDependencies =
    deps.databases.length > 0 || deps.caches.length > 0 || deps.queues.length > 0;
  const langColor =
    LANGUAGE_COLORS[deps.language.toLowerCase()] ??
    "bg-gray-500/15 text-gray-600 dark:text-gray-400 border-gray-500/30";

  async function handleProvision(serviceType: string) {
    if (!onProvision) return;
    setProvisioning(serviceType);
    try {
      onProvision(serviceType);
    } finally {
      setProvisioning(null);
    }
  }

  return (
    <div className="space-y-4">
      {/* Language & Framework */}
      <div className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg p-5">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-7 h-7 rounded-md bg-blue-500/10 flex items-center justify-center">
            <Code2 className="w-3.5 h-3.5 text-blue-500" />
          </div>
          <h4 className="text-sm font-semibold text-gray-900 dark:text-white">
            Language & Framework
          </h4>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge className={`border ${langColor} text-xs font-medium`}>
            {deps.language}
          </Badge>
          {deps.framework && (
            <Badge variant="outline" className="text-xs font-medium">
              {deps.framework}
            </Badge>
          )}
          {deps.has_dockerfile && (
            <Badge variant="secondary" className="text-xs font-medium">
              Dockerfile found
            </Badge>
          )}
        </div>
      </div>

      {/* Detected Dependencies */}
      {hasDependencies && (
        <div className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg p-5">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-7 h-7 rounded-md bg-purple-500/10 flex items-center justify-center">
              <Layers className="w-3.5 h-3.5 text-purple-500" />
            </div>
            <h4 className="text-sm font-semibold text-gray-900 dark:text-white">
              Detected Dependencies
            </h4>
          </div>
          <div className="space-y-3">
            {/* Databases */}
            {deps.databases.length > 0 && (
              <div>
                <p className="text-xs font-medium text-gray-500 dark:text-[#666] mb-1.5 uppercase tracking-wider">
                  Databases
                </p>
                <div className="flex flex-wrap gap-2">
                  {deps.databases.map((db) => {
                    const info = DB_ICONS[db.toLowerCase()] ?? {
                      label: db,
                      color: "text-gray-500",
                    };
                    return (
                      <div
                        key={db}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-gray-50 dark:bg-[#0a0a0a]"
                      >
                        <Database className={`w-3 h-3 ${info.color}`} />
                        <span className="text-xs font-medium text-gray-700 dark:text-[#ccc]">
                          {info.label}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Caches */}
            {deps.caches.length > 0 && (
              <div>
                <p className="text-xs font-medium text-gray-500 dark:text-[#666] mb-1.5 uppercase tracking-wider">
                  Caches
                </p>
                <div className="flex flex-wrap gap-2">
                  {deps.caches.map((cache) => {
                    const info = CACHE_ICONS[cache.toLowerCase()] ?? {
                      label: cache,
                      color: "text-gray-500",
                    };
                    return (
                      <div
                        key={cache}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-gray-50 dark:bg-[#0a0a0a]"
                      >
                        <Zap className={`w-3 h-3 ${info.color}`} />
                        <span className="text-xs font-medium text-gray-700 dark:text-[#ccc]">
                          {info.label}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Queues */}
            {deps.queues.length > 0 && (
              <div>
                <p className="text-xs font-medium text-gray-500 dark:text-[#666] mb-1.5 uppercase tracking-wider">
                  Queues
                </p>
                <div className="flex flex-wrap gap-2">
                  {deps.queues.map((queue) => {
                    const info = QUEUE_ICONS[queue.toLowerCase()] ?? {
                      label: queue,
                      color: "text-gray-500",
                    };
                    return (
                      <div
                        key={queue}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-gray-50 dark:bg-[#0a0a0a]"
                      >
                        <Server className={`w-3 h-3 ${info.color}`} />
                        <span className="text-xs font-medium text-gray-700 dark:text-[#ccc]">
                          {info.label}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Suggested Services */}
      {deps.suggested_services && deps.suggested_services.length > 0 && (
        <div className="bg-white dark:bg-[#141414] border border-blue-200 dark:border-blue-900/40 rounded-lg p-5">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-7 h-7 rounded-md bg-blue-500/10 flex items-center justify-center">
              <Plus className="w-3.5 h-3.5 text-blue-500" />
            </div>
            <h4 className="text-sm font-semibold text-gray-900 dark:text-white">
              Suggested Services
            </h4>
          </div>
          <div className="space-y-2">
            {deps.suggested_services.map((svc) => (
              <div
                key={svc.type}
                className="flex items-center justify-between gap-3 px-3 py-2.5 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-gray-50 dark:bg-[#0a0a0a]"
              >
                <div className="min-w-0">
                  <p className="text-xs font-medium text-gray-900 dark:text-white capitalize">
                    {svc.type}
                  </p>
                  <p className="text-xs text-gray-400 dark:text-[#555] truncate">{svc.reason}</p>
                </div>
                {onProvision && (
                  <button
                    type="button"
                    onClick={() => handleProvision(svc.type)}
                    disabled={provisioning === svc.type}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium transition-colors disabled:opacity-50 shrink-0"
                  >
                    {provisioning === svc.type ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : (
                      <Plus className="w-3 h-3" />
                    )}
                    Provision
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
