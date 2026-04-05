"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/ui/badge";
import { api, type Tenant, type ClusterHealth, type Deployment, type Application } from "@/lib/api";
import {
  FolderKanban,
  Box,
  CheckCircle2,
  AlertCircle,
  Loader2,
  ArrowRight,
  Clock,
  Plus,
  Zap,
  Activity,
  TrendingUp,
  Server,
} from "lucide-react";

interface RecentDeployment {
  tenantSlug: string;
  appSlug: string;
  appName: string;
  deployment: Deployment;
}

interface Stats {
  tenantCount: number;
  appCount: number;
  runningCount: number;
  buildCount: number;
  tenants: Tenant[];
  recentDeployments: RecentDeployment[];
}

const DEPLOY_STATUS_VARIANT: Record<string, "success" | "warning" | "destructive" | "secondary" | "default"> = {
  running: "success",
  building: "warning",
  deploying: "warning",
  pending: "secondary",
  failed: "destructive",
};

const STATUS_DOT: Record<string, string> = {
  running: "bg-emerald-500",
  building: "bg-amber-500 animate-pulse",
  deploying: "bg-blue-500 animate-pulse",
  pending: "bg-gray-400",
  failed: "bg-red-500",
};

// Material Dashboard style stat card with floating colored icon
function StatCard({
  label,
  value,
  icon: Icon,
  footer,
  gradient,
}: {
  label: string;
  value: string | number;
  icon: React.ElementType;
  footer?: string;
  gradient: string;
}) {
  return (
    <div className="stat-card">
      <div className={`stat-card-icon ${gradient}`}>
        <Icon className="w-7 h-7" />
      </div>
      <div className="pl-20">
        <p className="stat-card-label">{label}</p>
        <p className="stat-card-value">{value}</p>
      </div>
      {footer && (
        <div className="stat-card-footer flex items-center gap-1">
          <TrendingUp className="w-3 h-3 text-emerald-500" />
          <span>{footer}</span>
        </div>
      )}
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
    if (status !== "authenticated" || !accessToken) return;

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

        const appResults = await Promise.allSettled(
          tenantList.map((t) => api.apps.list(t.slug, accessToken))
        );
        const allApps: Array<{ tenant: Tenant; app: Application }> = [];
        appResults.forEach((r, i) => {
          if (r.status === "fulfilled") {
            r.value.forEach((app) => allApps.push({ tenant: tenantList[i], app }));
          }
        });

        const appsToCheck = allApps.slice(0, 10);
        const depResults = await Promise.allSettled(
          appsToCheck.map(({ tenant, app }) =>
            api.deployments.list(tenant.slug, app.slug, accessToken)
          )
        );

        const recentDeployments: RecentDeployment[] = [];
        let runningCount = 0;
        let buildCount = 0;
        depResults.forEach((r, i) => {
          if (r.status === "fulfilled" && r.value.length > 0) {
            const dep = r.value[0];
            if (dep.status === "running") runningCount++;
            if (dep.status === "building" || dep.status === "deploying") buildCount++;
            recentDeployments.push({
              tenantSlug: appsToCheck[i].tenant.slug,
              appSlug: appsToCheck[i].app.slug,
              appName: appsToCheck[i].app.name,
              deployment: dep,
            });
          }
        });

        recentDeployments.sort(
          (a, b) =>
            new Date(b.deployment.created_at).getTime() -
            new Date(a.deployment.created_at).getTime()
        );

        setStats({
          tenantCount: tenantList.length,
          appCount: allApps.length,
          runningCount,
          buildCount,
          tenants: tenantList,
          recentDeployments: recentDeployments.slice(0, 8),
        });
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
  const userName = session?.user?.name ?? session?.user?.email?.split("@")[0] ?? "there";

  return (
    <AppShell userEmail={session?.user?.email}>
      <div className="p-6 lg:p-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-gray-800 dark:text-white">Dashboard</h1>
          <p className="text-sm text-gray-500 mt-1">Welcome back, {userName}</p>
        </div>

        {/* Material Dashboard Stat Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-8 pt-4">
          <StatCard
            label="Projects"
            value={stats?.tenantCount ?? 0}
            icon={FolderKanban}
            gradient="bg-gradient-to-br from-orange-400 to-orange-600"
            footer={`${stats?.tenantCount ?? 0} namespaces`}
          />
          <StatCard
            label="Applications"
            value={stats?.appCount ?? 0}
            icon={Box}
            gradient="bg-gradient-to-br from-emerald-400 to-emerald-600"
            footer={`${stats?.runningCount ?? 0} running`}
          />
          <StatCard
            label="Running Pods"
            value={stats?.runningCount ?? 0}
            icon={Activity}
            gradient="bg-gradient-to-br from-red-400 to-red-600"
            footer="healthy instances"
          />
          <StatCard
            label="Cluster"
            value={clusterOk ? "Healthy" : "Degraded"}
            icon={Server}
            gradient={clusterOk ? "bg-gradient-to-br from-blue-400 to-blue-600" : "bg-gradient-to-br from-red-400 to-red-600"}
            footer={clusterOk ? "All nodes ready" : "Check cluster status"}
          />
        </div>

        {/* Quick Actions */}
        <div className="mb-8 flex items-center gap-3">
          <Link
            href="/tenants/new"
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white text-sm font-medium transition-all shadow-md shadow-emerald-500/20"
          >
            <Plus className="w-4 h-4" />
            New Project
          </Link>
          <Link
            href="/tenants"
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-white dark:bg-zinc-800 border border-gray-200 dark:border-zinc-700 text-gray-600 dark:text-zinc-300 hover:bg-gray-50 dark:hover:bg-zinc-700 text-sm font-medium transition-colors shadow-sm"
          >
            <Zap className="w-4 h-4" />
            View All Projects
          </Link>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Recent Projects */}
          <div className="bg-white dark:bg-zinc-900 rounded-xl shadow-md border border-gray-100 dark:border-zinc-800 overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-100 dark:border-zinc-800 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-gray-800 dark:text-white">Recent Projects</h2>
              <Link href="/tenants" className="text-xs text-blue-500 hover:text-blue-600 flex items-center gap-1">
                View all <ArrowRight className="w-3 h-3" />
              </Link>
            </div>
            {stats && stats.tenants.length > 0 ? (
              <div>
                {stats.tenants.slice(0, 5).map((tenant, i) => (
                  <Link
                    key={tenant.id}
                    href={`/tenants/${tenant.slug}`}
                    className={`flex items-center justify-between px-5 py-3.5 hover:bg-gray-50 dark:hover:bg-zinc-800/50 transition-colors group ${
                      i > 0 ? "border-t border-gray-50 dark:border-zinc-800/60" : ""
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-violet-400 to-violet-600 shadow-sm flex items-center justify-center">
                        <FolderKanban className="w-4 h-4 text-white" />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-gray-700 dark:text-zinc-200">{tenant.name}</p>
                        <p className="text-xs text-gray-400 font-mono">{tenant.slug}</p>
                      </div>
                    </div>
                    <Badge variant={tenant.active ? "success" : "secondary"}>
                      {tenant.active ? "active" : "inactive"}
                    </Badge>
                  </Link>
                ))}
              </div>
            ) : (
              <div className="text-center py-12">
                <FolderKanban className="w-10 h-10 mx-auto mb-3 text-gray-300" />
                <p className="text-sm text-gray-500">No projects yet.</p>
                <Link href="/tenants/new" className="inline-block mt-3 text-sm text-emerald-500 hover:text-emerald-600">
                  Create your first project →
                </Link>
              </div>
            )}
          </div>

          {/* Recent Activity */}
          <div className="bg-white dark:bg-zinc-900 rounded-xl shadow-md border border-gray-100 dark:border-zinc-800 overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-100 dark:border-zinc-800">
              <h2 className="text-sm font-semibold text-gray-800 dark:text-white">Recent Activity</h2>
            </div>
            {stats && stats.recentDeployments.length > 0 ? (
              <div>
                {stats.recentDeployments.map((item, i) => (
                  <Link
                    key={item.deployment.id}
                    href={`/tenants/${item.tenantSlug}/apps/${item.appSlug}`}
                    className={`flex items-center justify-between px-5 py-3.5 hover:bg-gray-50 dark:hover:bg-zinc-800/50 transition-colors ${
                      i > 0 ? "border-t border-gray-50 dark:border-zinc-800/60" : ""
                    }`}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className={`w-2.5 h-2.5 rounded-full shrink-0 ${STATUS_DOT[item.deployment.status] ?? "bg-gray-400"}`} />
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-gray-700 dark:text-zinc-200 truncate">
                          {item.appName}
                          <span className="ml-2 text-xs text-gray-400 font-mono">{item.tenantSlug}</span>
                        </p>
                        <span className="flex items-center gap-1 text-xs text-gray-400">
                          <Clock className="w-3 h-3" />
                          {new Date(item.deployment.created_at).toLocaleString()}
                        </span>
                      </div>
                    </div>
                    <Badge variant={DEPLOY_STATUS_VARIANT[item.deployment.status] ?? "secondary"}>
                      {item.deployment.status}
                    </Badge>
                  </Link>
                ))}
              </div>
            ) : (
              <div className="text-center py-12">
                <Activity className="w-10 h-10 mx-auto mb-3 text-gray-300" />
                <p className="text-sm text-gray-500">No recent deployments.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
