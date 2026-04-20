"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/ui/badge";
import { api, type Tenant } from "@/lib/api";
import { FolderKanban, Plus, Loader2, ArrowRight, Search } from "lucide-react";

export default function TenantsPage() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  const accessToken = (session as typeof session & { accessToken?: string })?.accessToken;
  const platformAdmin = (session as typeof session & { platformAdmin?: boolean })?.platformAdmin ?? false;

  useEffect(() => {
    if (status === "unauthenticated") router.push("/auth/signin");
  }, [status, router]);

  useEffect(() => {
    if (status !== "authenticated") return;
    api.tenants
      .list(accessToken)
      .then(setTenants)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [status, accessToken]);

  if (status === "loading" || (status === "authenticated" && loading)) {
    return (
      <AppShell userEmail={session?.user?.email}>
        <div className="flex items-center justify-center h-full min-h-[400px]">
          <Loader2 className="w-5 h-5 animate-spin text-gray-400 dark:text-zinc-600" />
        </div>
      </AppShell>
    );
  }

  const filtered = search
    ? tenants.filter(
        (t) =>
          t.name.toLowerCase().includes(search.toLowerCase()) ||
          t.slug.toLowerCase().includes(search.toLowerCase())
      )
    : tenants;

  return (
    <AppShell userEmail={session?.user?.email}>
      <div className="p-6 lg:p-8">
        {/* Page header */}
        <div className="flex items-start justify-between mb-6">
          <div>
            <p className="text-xs text-gray-500 dark:text-zinc-500 mb-1 uppercase tracking-wider">Platform</p>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-zinc-100">Projects</h1>
            <p className="text-sm text-gray-500 dark:text-zinc-500 mt-1">
              {tenants.length} project{tenants.length !== 1 ? "s" : ""}
            </p>
          </div>
          {platformAdmin && (
            <Link
              href="/tenants/new"
              data-testid="tenants-new-project"
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              New Project
            </Link>
          )}
        </div>

        {/* Search */}
        {tenants.length > 0 && (
          <div className="relative mb-4">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 dark:text-zinc-600" />
            <input
              type="text"
              placeholder="Search projects..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-2 bg-white dark:bg-zinc-900/50 border border-gray-200 dark:border-zinc-800 rounded-lg text-sm text-gray-800 dark:text-zinc-200 placeholder:text-gray-400 dark:placeholder:text-zinc-600 focus:outline-none focus:border-gray-300 dark:focus:border-zinc-700 focus:ring-1 focus:ring-gray-300 dark:focus:ring-zinc-700 transition-colors"
            />
          </div>
        )}

        {filtered.length === 0 && tenants.length === 0 ? (
          <div className="text-center py-20 border border-dashed border-gray-200 dark:border-zinc-800 rounded-xl" data-testid="tenants-empty">
            <FolderKanban className="w-10 h-10 mx-auto mb-3 text-gray-400 dark:text-zinc-700" />
            {platformAdmin ? (
              <>
                <p className="text-sm text-gray-500 dark:text-zinc-500">No projects yet.</p>
                <Link
                  href="/tenants/new"
                  className="inline-block mt-3 text-sm text-emerald-500 hover:text-emerald-400 transition-colors"
                >
                  Create your first project →
                </Link>
              </>
            ) : (
              <>
                <p className="text-sm text-gray-500 dark:text-zinc-500">
                  You haven&apos;t been assigned to a project yet.
                </p>
                <p className="text-xs text-gray-400 dark:text-zinc-600 mt-2">
                  Contact your administrator to be added to one.
                </p>
              </>
            )}
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-12 text-gray-400 dark:text-zinc-600">
            <p className="text-sm">No projects match &ldquo;{search}&rdquo;</p>
          </div>
        ) : (
          <div className="bg-white dark:bg-zinc-900/50 border border-gray-200 dark:border-zinc-800 rounded-xl overflow-hidden shadow-sm">
            {filtered.map((tenant, i) => (
              <Link
                key={tenant.id}
                href={`/tenants/${tenant.slug}`}
                className={`flex items-center justify-between px-4 py-4 hover:bg-gray-50 dark:hover:bg-zinc-800/50 transition-colors group ${
                  i > 0 ? "border-t border-gray-100 dark:border-zinc-800/60" : ""
                }`}
              >
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-xl bg-violet-500/10 border border-violet-500/20 flex items-center justify-center shrink-0">
                    <FolderKanban className="w-4 h-4 text-violet-400" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-gray-800 dark:text-zinc-200 group-hover:text-gray-900 dark:group-hover:text-zinc-100 transition-colors">
                      {tenant.name}
                    </p>
                    <p className="text-xs text-gray-400 dark:text-zinc-600 font-mono mt-0.5">
                      {tenant.namespace}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="hidden sm:flex items-center gap-3 text-xs text-gray-400 dark:text-zinc-600 font-mono">
                    <span className="px-2 py-0.5 rounded bg-gray-100 dark:bg-zinc-800 text-gray-500 dark:text-zinc-500">{tenant.cpu_limit} CPU</span>
                    <span className="px-2 py-0.5 rounded bg-gray-100 dark:bg-zinc-800 text-gray-500 dark:text-zinc-500">{tenant.memory_limit}</span>
                    <span className="px-2 py-0.5 rounded bg-gray-100 dark:bg-zinc-800 text-gray-500 dark:text-zinc-500">{tenant.storage_limit}</span>
                  </div>
                  <Badge variant={tenant.active ? "success" : "secondary"}>
                    {tenant.active ? "active" : "inactive"}
                  </Badge>
                  <ArrowRight className="w-3.5 h-3.5 text-gray-400 dark:text-zinc-700 group-hover:text-gray-500 dark:group-hover:text-zinc-500 transition-colors" />
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
