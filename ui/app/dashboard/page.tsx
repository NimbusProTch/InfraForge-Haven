"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/ui/badge";
import { api, type Tenant, type ClusterHealth } from "@/lib/api";
import { Building2, Box, CheckCircle2, AlertCircle, Loader2, ArrowRight } from "lucide-react";

interface Stats {
  tenantCount: number;
  appCount: number;
  tenants: Tenant[];
}

function StatCard({
  label,
  value,
  icon: Icon,
  sub,
}: {
  label: string;
  value: string | number;
  icon: React.ElementType;
  sub?: string;
}) {
  return (
    <div className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg p-5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm text-gray-500 dark:text-[#888]">{label}</span>
        <div className="w-8 h-8 rounded-md bg-gray-100 dark:bg-[#1f1f1f] flex items-center justify-center">
          <Icon className="w-4 h-4 text-gray-500 dark:text-[#666]" />
        </div>
      </div>
      <p className="text-2xl font-semibold text-gray-900 dark:text-white">{value}</p>
      {sub && <p className="text-xs text-gray-400 dark:text-[#555] mt-1">{sub}</p>}
    </div>
  );
}

export default function DashboardPage() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const [stats, setStats] = useState<Stats | null>(null);
  const [cluster, setCluster] = useState<ClusterHealth | null>(null);
  const [loading, setLoading] = useState(true);

  const accessToken = (session as typeof session & { accessToken?: string })?.accessToken;

  useEffect(() => {
    if (status === "unauthenticated") {
      router.push("/auth/signin");
    }
  }, [status, router]);

  useEffect(() => {
    if (status !== "authenticated") return;

    async function load() {
      try {
        const [tenants, clusterHealth] = await Promise.allSettled([
          api.tenants.list(accessToken),
          api.health.cluster(),
        ]);

        let tenantList: Tenant[] = [];
        if (tenants.status === "fulfilled") {
          tenantList = tenants.value;
        }

        if (clusterHealth.status === "fulfilled") {
          setCluster(clusterHealth.value);
        }

        // Fetch app counts in parallel
        const appResults = await Promise.allSettled(
          tenantList.map((t) => api.apps.list(t.slug, accessToken))
        );
        const totalApps = appResults.reduce((acc, r) => {
          return acc + (r.status === "fulfilled" ? r.value.length : 0);
        }, 0);

        setStats({ tenantCount: tenantList.length, appCount: totalApps, tenants: tenantList });
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [status, accessToken]);

  if (status === "loading" || loading) {
    return (
      <AppShell userEmail={session?.user?.email}>
        <div className="flex items-center justify-center h-full min-h-[400px]">
          <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
        </div>
      </AppShell>
    );
  }

  const clusterOk = cluster?.status === "ok";

  return (
    <AppShell userEmail={session?.user?.email}>
      <div className="p-6 max-w-5xl">
        {/* Page header */}
        <div className="mb-8">
          <h1 className="text-xl font-semibold text-gray-900 dark:text-white">Dashboard</h1>
          <p className="text-sm text-gray-500 dark:text-[#888] mt-1">
            Haven Platform overview
          </p>
        </div>

        {/* Stats grid */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
          <StatCard
            label="Tenants"
            value={stats?.tenantCount ?? 0}
            icon={Building2}
            sub="registered organizations"
          />
          <StatCard
            label="Applications"
            value={stats?.appCount ?? 0}
            icon={Box}
            sub="across all tenants"
          />
          <div className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm text-gray-500 dark:text-[#888]">Cluster</span>
              <div className="w-8 h-8 rounded-md bg-gray-100 dark:bg-[#1f1f1f] flex items-center justify-center">
                {clusterOk ? (
                  <CheckCircle2 className="w-4 h-4 text-green-500" />
                ) : (
                  <AlertCircle className="w-4 h-4 text-red-500" />
                )}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <p className="text-2xl font-semibold text-gray-900 dark:text-white capitalize">
                {cluster?.status ?? "—"}
              </p>
              {cluster && (
                <Badge variant={clusterOk ? "success" : "destructive"}>
                  {clusterOk ? "healthy" : "degraded"}
                </Badge>
              )}
            </div>
            <p className="text-xs text-gray-400 dark:text-[#555] mt-1">kubernetes cluster</p>
          </div>
        </div>

        {/* Recent tenants */}
        {stats && stats.tenants.length > 0 && (
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-medium text-gray-900 dark:text-white">
                Tenants
              </h2>
              <Link
                href="/tenants"
                className="text-xs text-gray-500 dark:text-[#666] hover:text-gray-900 dark:hover:text-white flex items-center gap-1 transition-colors"
              >
                View all <ArrowRight className="w-3 h-3" />
              </Link>
            </div>
            <div className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg overflow-hidden">
              {stats.tenants.slice(0, 5).map((tenant, i) => (
                <Link
                  key={tenant.id}
                  href={`/tenants/${tenant.slug}`}
                  className={`flex items-center justify-between px-4 py-3 hover:bg-gray-50 dark:hover:bg-[#1a1a1a] transition-colors ${
                    i > 0 ? "border-t border-gray-100 dark:border-[#1e1e1e]" : ""
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div className="w-7 h-7 rounded-md bg-blue-600/10 dark:bg-blue-600/20 flex items-center justify-center">
                      <Building2 className="w-3.5 h-3.5 text-blue-600" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-gray-900 dark:text-white">
                        {tenant.name}
                      </p>
                      <p className="text-xs text-gray-400 dark:text-[#555] font-mono">
                        {tenant.slug}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={tenant.active ? "success" : "secondary"}>
                      {tenant.active ? "active" : "inactive"}
                    </Badge>
                    <ArrowRight className="w-3.5 h-3.5 text-gray-400 dark:text-[#444]" />
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )}

        {stats?.tenants.length === 0 && (
          <div className="text-center py-16 text-gray-400 dark:text-[#555]">
            <Building2 className="w-10 h-10 mx-auto mb-3 opacity-40" />
            <p className="text-sm">No tenants yet.</p>
            <Link
              href="/tenants/new"
              className="inline-block mt-3 text-sm text-blue-600 hover:text-blue-500"
            >
              Create your first tenant →
            </Link>
          </div>
        )}
      </div>
    </AppShell>
  );
}
