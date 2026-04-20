"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { api, type AccessRequest, type Tenant } from "@/lib/api";
import { Loader2, Inbox, FolderKanban, UserPlus, ArrowRight } from "lucide-react";

interface Counters {
  pending: number;
  approved: number;
  rejected: number;
  tenants: number;
}

export default function AdminHomePage() {
  const { data: session, status } = useSession();
  const [counters, setCounters] = useState<Counters | null>(null);
  const [loading, setLoading] = useState(true);

  const accessToken = (session as typeof session & { accessToken?: string })?.accessToken;

  useEffect(() => {
    if (status !== "authenticated" || !accessToken) return;

    async function load() {
      try {
        const [reqs, tenants] = await Promise.all<[Promise<AccessRequest[]>, Promise<Tenant[]>]>([
          api.accessRequests.list(accessToken).catch(() => [] as AccessRequest[]),
          api.tenants.list(accessToken).catch(() => [] as Tenant[]),
        ]);
        const by = (s: AccessRequest["status"]) => reqs.filter((r) => r.status === s).length;
        setCounters({
          pending: by("pending"),
          approved: by("approved"),
          rejected: by("rejected"),
          tenants: tenants.length,
        });
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [status, accessToken]);

  if (loading) {
    return (
      <AppShell userEmail={session?.user?.email}>
        <div className="flex items-center justify-center h-full min-h-[400px]">
          <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell userEmail={session?.user?.email}>
      <div className="p-6 lg:p-8">
        <div className="mb-8">
          <p className="text-xs text-gray-500 dark:text-zinc-500 uppercase tracking-wider">
            Platform administration
          </p>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white mt-1">
            Admin console
          </h1>
          <p className="text-sm text-gray-500 dark:text-zinc-500 mt-1">
            Review enterprise-access requests and provision new tenants.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <AdminCard
            href="/admin/access-requests"
            icon={<Inbox className="w-5 h-5" />}
            title="Access requests"
            subtitle={`${counters?.pending ?? 0} pending · ${counters?.approved ?? 0} approved · ${
              counters?.rejected ?? 0
            } rejected`}
            badge={counters?.pending ? String(counters.pending) : undefined}
            testid="admin-card-access-requests"
          />
          <AdminCard
            href="/tenants/new"
            icon={<UserPlus className="w-5 h-5" />}
            title="Provision new tenant"
            subtitle="Create a tenant, add an owner, and hand over a set-password link."
            testid="admin-card-new-tenant"
          />
          <AdminCard
            href="/tenants"
            icon={<FolderKanban className="w-5 h-5" />}
            title="All tenants"
            subtitle={`${counters?.tenants ?? 0} project${counters?.tenants === 1 ? "" : "s"} in the cluster`}
            testid="admin-card-all-tenants"
          />
        </div>
      </div>
    </AppShell>
  );
}

function AdminCard({
  href,
  icon,
  title,
  subtitle,
  badge,
  testid,
}: {
  href: string;
  icon: React.ReactNode;
  title: string;
  subtitle: string;
  badge?: string;
  testid?: string;
}) {
  return (
    <Link
      href={href}
      data-testid={testid}
      className="group flex items-start gap-4 rounded-xl border border-gray-200 dark:border-zinc-800 bg-white dark:bg-zinc-900/50 p-5 shadow-sm hover:border-indigo-300 dark:hover:border-indigo-700 hover:shadow-md transition-all"
    >
      <div className="w-10 h-10 rounded-lg bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400 flex items-center justify-center flex-shrink-0">
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-semibold text-gray-900 dark:text-white">{title}</p>
          {badge && (
            <span className="px-1.5 py-0.5 rounded-full bg-rose-100 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 text-xs font-medium">
              {badge}
            </span>
          )}
        </div>
        <p className="text-xs text-gray-500 dark:text-zinc-500 mt-1">{subtitle}</p>
      </div>
      <ArrowRight className="w-4 h-4 text-gray-400 dark:text-zinc-600 group-hover:text-indigo-500 transition-colors" />
    </Link>
  );
}
