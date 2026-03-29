"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import {
  Loader2,
  FileText,
  ChevronLeft,
  ChevronRight,
  Search,
  Filter,
} from "lucide-react";

interface AuditLog {
  id: string;
  tenant_id: string;
  user_id: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  details: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
}

interface AuditLogList {
  items: AuditLog[];
  total: number;
}

const ACTION_COLORS: Record<string, string> = {
  create: "text-emerald-500",
  update: "text-blue-500",
  delete: "text-red-500",
  deploy: "text-amber-500",
  login: "text-violet-500",
  invite: "text-cyan-500",
};

interface AuditLogsTabProps {
  tenantSlug: string;
  accessToken?: string;
}

export default function AuditLogsTab({ tenantSlug, accessToken }: AuditLogsTabProps) {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [actionFilter, setActionFilter] = useState("");
  const [resourceFilter, setResourceFilter] = useState("");
  const pageSize = 20;

  const loadLogs = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {
        page: String(page),
        page_size: String(pageSize),
      };
      if (actionFilter) params.action = actionFilter;
      if (resourceFilter) params.resource_type = resourceFilter;

      const result = await api.audit.list(tenantSlug, params, accessToken) as unknown as AuditLogList;
      setLogs(result.items ?? []);
      setTotal(result.total ?? 0);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [tenantSlug, accessToken, page, actionFilter, resourceFilter]);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  const totalPages = Math.ceil(total / pageSize);

  return (
    <div>
      {/* Header + filters */}
      <div className="flex items-center justify-between mb-5">
        <p className="text-sm text-zinc-500">
          {total} event{total !== 1 ? "s" : ""} recorded
        </p>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Filter className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3 h-3 text-zinc-600" />
            <select
              value={actionFilter}
              onChange={(e) => { setActionFilter(e.target.value); setPage(1); }}
              className="appearance-none bg-zinc-800 border border-zinc-700 rounded-lg pl-7 pr-3 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-blue-600"
            >
              <option value="">All actions</option>
              <option value="create">Create</option>
              <option value="update">Update</option>
              <option value="delete">Delete</option>
              <option value="deploy">Deploy</option>
              <option value="login">Login</option>
            </select>
          </div>
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3 h-3 text-zinc-600" />
            <input
              type="text"
              value={resourceFilter}
              onChange={(e) => { setResourceFilter(e.target.value); setPage(1); }}
              placeholder="Filter by resource"
              className="bg-zinc-800 border border-zinc-700 rounded-lg pl-7 pr-3 py-1.5 text-xs text-zinc-300 placeholder:text-zinc-600 focus:outline-none focus:border-blue-600 w-40"
            />
          </div>
        </div>
      </div>

      {/* Log table */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="w-5 h-5 animate-spin text-zinc-600" />
        </div>
      ) : logs.length === 0 ? (
        <div className="text-center py-16 border border-dashed border-zinc-800 rounded-xl">
          <FileText className="w-8 h-8 mx-auto mb-2 text-zinc-700" />
          <p className="text-sm text-zinc-500">No audit logs found.</p>
          <p className="text-xs text-zinc-600 mt-1">Actions will appear here as team members use the platform.</p>
        </div>
      ) : (
        <>
          <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-zinc-800">
                  <th className="text-left text-xs font-medium text-zinc-600 px-4 py-2.5">Time</th>
                  <th className="text-left text-xs font-medium text-zinc-600 px-4 py-2.5">User</th>
                  <th className="text-left text-xs font-medium text-zinc-600 px-4 py-2.5">Action</th>
                  <th className="text-left text-xs font-medium text-zinc-600 px-4 py-2.5">Resource</th>
                  <th className="text-left text-xs font-medium text-zinc-600 px-4 py-2.5">Details</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => {
                  const actionColor = ACTION_COLORS[log.action] ?? "text-zinc-400";
                  return (
                    <tr key={log.id} className="border-b border-zinc-800/50 last:border-0 hover:bg-zinc-800/30">
                      <td className="text-xs text-zinc-500 px-4 py-2.5 font-mono whitespace-nowrap">
                        {new Date(log.created_at).toLocaleString()}
                      </td>
                      <td className="text-xs text-zinc-400 px-4 py-2.5 font-mono truncate max-w-[120px]">
                        {log.user_id ?? "system"}
                      </td>
                      <td className="px-4 py-2.5">
                        <span className={`text-xs font-medium ${actionColor}`}>
                          {log.action}
                        </span>
                      </td>
                      <td className="px-4 py-2.5">
                        {log.resource_type && (
                          <div className="flex items-center gap-1.5">
                            <Badge variant="secondary">{log.resource_type}</Badge>
                            {log.resource_id && (
                              <span className="text-xs text-zinc-600 font-mono truncate max-w-[100px]">
                                {log.resource_id}
                              </span>
                            )}
                          </div>
                        )}
                      </td>
                      <td className="text-xs text-zinc-600 px-4 py-2.5 font-mono truncate max-w-[200px]">
                        {log.details ? JSON.stringify(log.details).slice(0, 60) : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-4">
              <p className="text-xs text-zinc-600">
                Page {page} of {totalPages} ({total} total)
              </p>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="p-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-400 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                >
                  <ChevronLeft className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  className="p-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-400 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                >
                  <ChevronRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
