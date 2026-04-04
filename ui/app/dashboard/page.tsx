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
  pending: "bg-zinc-500",
  failed: "bg-red-500",
};

function StatCard({
  label,
  value,
  icon: Icon,
  sub,
  accent,
}: {
  label: string;
  value: string | number;
  icon: React.ElementType;
  sub?: string;
  accent?: string;
}) {
  return (
    <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-5 hover:border-zinc-700 transition-colors">
      <div className="flex items-center justify-between mb-4">
        <span className="text-xs font-medium text-zinc-500 uppercase tracking-wider">{label}</span>
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${accent ?? "bg-zinc-800"}`}>
          <Icon className="w-4 h-4 text-zinc-400" />
        </div>
      </div>
      <p className="text-3xl font-bold text-zinc-100">{value}</p>
      {sub && <p className="text-xs text-zinc-500 mt-1.5">{sub}</p>}
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
          <Loader2 className="w-5 h-5 animate-spin text-zinc-600" />
        </div>
      </AppShell>
    );
  }

  const clusterOk = cluster?.status === "ok";
  const userName = session?.user?.name ?? session?.user?.email?.split("@")[0] ?? "there";

  return (
    <AppShell userEmail={session?.user?.email}>
      <div className="p-6 max-w-5xl">
        {/* Header */}
        <div className="mb-8">
          <p className="text-xs text-zinc-500 mb-1 uppercase tracking-wider">Overview</p>
          <h1 className="text-2xl font-bold text-zinc-100">Welcome back, {userName}</h1>
          <p className="text-sm text-zinc-500 mt-1">Haven Platform · Self-Service DevOps</p>
        </div>

        {/* Stats grid */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <StatCard
            label="Projects"
            value={stats?.tenantCount ?? 0}
            icon={FolderKanban}
            sub="namespaces"
            accent="bg-violet-500/10"
          />
          <StatCard
            label="Applications"
            value={stats?.appCount ?? 0}
            icon={Box}
            sub={`${stats?.runningCount ?? 0} running`}
            accent="bg-blue-500/10"
          />
          <StatCard
            label="Running"
            value={stats?.runningCount ?? 0}
            icon={Activity}
            sub="healthy pods"
            accent="bg-emerald-500/10"
          />
          <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-5 hover:border-zinc-700 transition-colors">
            <div className="flex items-center justify-between mb-4">
              <span className="text-xs font-medium text-zinc-500 uppercase tracking-wider">Cluster</span>
              <div className="w-8 h-8 rounded-lg bg-zinc-800 flex items-center justify-center">
                {clusterOk ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                ) : (
                  <AlertCircle className="w-4 h-4 text-red-500" />
                )}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <p className="text-3xl font-bold text-zinc-100 capitalize">
                {cluster?.status ?? "—"}
              </p>
            </div>
            <div className="flex items-center gap-1.5 mt-1.5">
              <span className={`w-1.5 h-1.5 rounded-full ${clusterOk ? "bg-emerald-500" : "bg-red-500"}`} />
              <p className="text-xs text-zinc-500">{clusterOk ? "healthy" : "degraded"}</p>
            </div>
          </div>
        </div>

        {/* Quick Actions */}
        <div className="mb-8">
          <h2 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-3">
            Quick Actions
          </h2>
          <div className="flex items-center gap-3">
            <Link
              href="/tenants/new"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium transition-colors"
            >
              <Plus className="w-4 h-4" />
              New Project
            </Link>
            <Link
              href="/tenants"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-zinc-800 hover:border-zinc-700 text-zinc-400 hover:text-zinc-200 text-sm font-medium transition-colors"
            >
              <Zap className="w-4 h-4" />
              View All Projects
            </Link>
          </div>
        </div>

        {/* Recent projects */}
        {stats && stats.tenants.length > 0 && (
          <div className="mb-8">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-xs font-medium text-zinc-500 uppercase tracking-wider">
                Recent Projects
              </h2>
              <Link
                href="/tenants"
                className="text-xs text-zinc-600 hover:text-zinc-300 flex items-center gap-1 transition-colors"
              >
                View all <ArrowRight className="w-3 h-3" />
              </Link>
            </div>
            <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl overflow-hidden">
              {stats.tenants.slice(0, 5).map((tenant, i) => (
                <Link
                  key={tenant.id}
                  href={`/tenants/${tenant.slug}`}
                  className={`flex items-center justify-between px-4 py-3.5 hover:bg-zinc-800/50 transition-colors group ${
                    i > 0 ? "border-t border-zinc-800/60" : ""
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-violet-500/10 border border-violet-500/20 flex items-center justify-center">
                      <FolderKanban className="w-3.5 h-3.5 text-violet-400" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-zinc-200 group-hover:text-zinc-100 transition-colors">
                        {tenant.name}
                      </p>
                      <p className="text-xs text-zinc-600 font-mono">{tenant.slug}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={tenant.active ? "success" : "secondary"}>
                      {tenant.active ? "active" : "inactive"}
                    </Badge>
                    <ArrowRight className="w-3.5 h-3.5 text-zinc-700 group-hover:text-zinc-500 transition-colors" />
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )}

        {stats?.tenants.length === 0 && (
          <div className="text-center py-16 border border-dashed border-zinc-800 rounded-xl">
            <FolderKanban className="w-10 h-10 mx-auto mb-3 text-zinc-700" />
            <p className="text-sm text-zinc-500">No projects yet.</p>
            <Link
              href="/tenants/new"
              className="inline-block mt-3 text-sm text-emerald-500 hover:text-emerald-400 transition-colors"
            >
              Create your first project →
            </Link>
          </div>
        )}

        {/* Recent Deployments */}
        {stats && stats.recentDeployments.length > 0 && (
          <div>
            <h2 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-3">
              Recent Activity
            </h2>
            <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl overflow-hidden">
              {stats.recentDeployments.map((item, i) => (
                <Link
                  key={item.deployment.id}
                  href={`/tenants/${item.tenantSlug}/apps/${item.appSlug}`}
                  className={`flex items-center justify-between px-4 py-3.5 hover:bg-zinc-800/50 transition-colors group ${
                    i > 0 ? "border-t border-zinc-800/60" : ""
                  }`}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div
                      className={`w-2 h-2 rounded-full shrink-0 ${STATUS_DOT[item.deployment.status] ?? "bg-zinc-500"}`}
                    />
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium text-zinc-200 truncate">
                          {item.appName}
                        </p>
                        <span className="text-xs text-zinc-600 shrink-0 font-mono">
                          {item.tenantSlug}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 mt-0.5">
                        {item.deployment.commit_sha && (
                          <span className="text-xs font-mono text-zinc-600">
                            {item.deployment.commit_sha.slice(0, 7)}
                          </span>
                        )}
                        <span className="flex items-center gap-1 text-xs text-zinc-600">
                          <Clock className="w-3 h-3" />
                          {new Date(item.deployment.created_at).toLocaleString()}
                        </span>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0 ml-3">
                    <Badge variant={DEPLOY_STATUS_VARIANT[item.deployment.status] ?? "secondary"}>
                      {item.deployment.status}
                    </Badge>
                    <ArrowRight className="w-3.5 h-3.5 text-zinc-700 group-hover:text-zinc-500 transition-colors" />
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
