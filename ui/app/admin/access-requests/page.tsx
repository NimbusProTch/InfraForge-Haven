"use client";

import { useEffect, useMemo, useState } from "react";
import { useSession } from "next-auth/react";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/ui/badge";
import { api, type AccessRequest, type AccessRequestStatus } from "@/lib/api";
import {
  ArrowLeft,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  Building2,
  Mail,
  AlertCircle,
} from "lucide-react";

const STATUS_VARIANT: Record<AccessRequestStatus, "warning" | "success" | "destructive"> = {
  pending: "warning",
  approved: "success",
  rejected: "destructive",
};

const FILTERS: { value: AccessRequestStatus | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "pending", label: "Pending" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
];

export default function AdminAccessRequestsPage() {
  const { data: session } = useSession();
  const [filter, setFilter] = useState<AccessRequestStatus | "all">("pending");
  const [items, setItems] = useState<AccessRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState("");

  const accessToken = (session as typeof session & { accessToken?: string })?.accessToken;

  useEffect(() => {
    if (!accessToken) return;
    setLoading(true);
    const target = filter === "all" ? undefined : filter;
    api.accessRequests
      .list(accessToken, target)
      .then(setItems)
      .catch((e: Error) => setError(e.message || "Failed to load"))
      .finally(() => setLoading(false));
  }, [accessToken, filter]);

  const counts = useMemo(() => {
    const by = (s: AccessRequestStatus) => items.filter((i) => i.status === s).length;
    return {
      all: items.length,
      pending: by("pending"),
      approved: by("approved"),
      rejected: by("rejected"),
    };
  }, [items]);

  async function review(id: string, status: "approved" | "rejected") {
    setBusyId(id);
    setError("");
    try {
      const updated = await api.accessRequests.review(id, { status }, accessToken);
      setItems((xs) => xs.map((x) => (x.id === id ? updated : x)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Review failed");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <AppShell userEmail={session?.user?.email}>
      <div className="p-6 lg:p-8 max-w-5xl">
        <div className="flex items-center gap-3 mb-6">
          <Link
            href="/admin"
            className="text-gray-400 hover:text-gray-900 dark:text-zinc-500 dark:hover:text-white transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div>
            <h1 className="text-xl font-bold text-gray-900 dark:text-white">Access requests</h1>
            <p className="text-sm text-gray-500 dark:text-zinc-500 mt-0.5">
              Prospective customers who filled the public request-access form.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 mb-6">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              onClick={() => setFilter(f.value)}
              data-testid={`filter-${f.value}`}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                filter === f.value
                  ? "bg-indigo-600 text-white"
                  : "bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-800 text-gray-600 dark:text-zinc-400 hover:bg-gray-50 dark:hover:bg-zinc-800"
              }`}
            >
              {f.label}
              {f.value !== "all" && counts[f.value] > 0 && (
                <span className="ml-1.5 opacity-70">({counts[f.value]})</span>
              )}
            </button>
          ))}
        </div>

        {error && (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-900 dark:border-red-800/50 dark:bg-red-950/40 dark:text-red-300 mb-4"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
          </div>
        ) : items.length === 0 ? (
          <div
            className="text-center py-20 border border-dashed border-gray-200 dark:border-zinc-800 rounded-xl"
            data-testid="access-requests-empty"
          >
            <Mail className="w-10 h-10 mx-auto mb-3 text-gray-400 dark:text-zinc-700" />
            <p className="text-sm text-gray-500 dark:text-zinc-500">
              No {filter === "all" ? "" : filter} access requests.
            </p>
          </div>
        ) : (
          <div className="space-y-3" data-testid="access-requests-list">
            {items.map((item) => (
              <RequestCard
                key={item.id}
                item={item}
                busy={busyId === item.id}
                onApprove={() => review(item.id, "approved")}
                onReject={() => review(item.id, "rejected")}
              />
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}

function RequestCard({
  item,
  busy,
  onApprove,
  onReject,
}: {
  item: AccessRequest;
  busy: boolean;
  onApprove: () => void;
  onReject: () => void;
}) {
  const createdAt = new Date(item.created_at).toLocaleString();
  const reviewedAt = item.reviewed_at ? new Date(item.reviewed_at).toLocaleString() : null;
  const canReview = item.status === "pending";

  return (
    <div
      data-testid={`access-request-${item.id}`}
      className="bg-white dark:bg-zinc-900/60 border border-gray-200 dark:border-zinc-800 rounded-xl p-5 shadow-sm"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-semibold text-gray-900 dark:text-white">{item.name}</p>
            <Badge variant={STATUS_VARIANT[item.status]}>{item.status}</Badge>
          </div>
          <div className="mt-1.5 flex items-center gap-3 text-xs text-gray-500 dark:text-zinc-500 flex-wrap">
            <span className="flex items-center gap-1">
              <Mail className="w-3 h-3" />
              <a href={`mailto:${item.email}`} className="hover:underline">
                {item.email}
              </a>
            </span>
            <span className="flex items-center gap-1">
              <Building2 className="w-3 h-3" />
              {item.org_name}
            </span>
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {createdAt}
            </span>
          </div>
          {item.message && (
            <p className="mt-3 text-sm text-gray-700 dark:text-zinc-300 whitespace-pre-wrap">
              {item.message}
            </p>
          )}
          {reviewedAt && (
            <p className="mt-3 text-xs text-gray-400 dark:text-zinc-600">
              Reviewed {reviewedAt}
              {item.reviewed_by ? ` by ${item.reviewed_by}` : ""}
              {item.review_notes ? ` — ${item.review_notes}` : ""}
            </p>
          )}
        </div>

        {canReview && (
          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              type="button"
              onClick={onApprove}
              disabled={busy}
              data-testid={`approve-${item.id}`}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white text-xs font-medium transition-colors"
            >
              {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle2 className="w-3 h-3" />}
              Approve
            </button>
            <button
              type="button"
              onClick={onReject}
              disabled={busy}
              data-testid={`reject-${item.id}`}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-800 hover:bg-gray-50 dark:hover:bg-zinc-800 disabled:opacity-60 text-gray-700 dark:text-zinc-300 text-xs font-medium transition-colors"
            >
              <XCircle className="w-3 h-3" />
              Reject
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
