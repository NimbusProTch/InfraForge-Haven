"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/ui/badge";
import { api, type Tenant } from "@/lib/api";
import { Building2, Plus, Loader2, ArrowRight } from "lucide-react";

export default function TenantsPage() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);

  const accessToken = (session as typeof session & { accessToken?: string })?.accessToken;

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

  if (status === "loading" || loading) {
    return (
      <AppShell userEmail={session?.user?.email}>
        <div className="flex items-center justify-center h-full min-h-[400px]">
          <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell userEmail={session?.user?.email}>
      <div className="p-6 max-w-5xl">
        {/* Page header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">Tenants</h1>
            <p className="text-sm text-gray-500 dark:text-[#888] mt-1">
              {tenants.length} organization{tenants.length !== 1 ? "s" : ""}
            </p>
          </div>
          <Link
            href="/tenants/new"
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            New Tenant
          </Link>
        </div>

        {tenants.length === 0 ? (
          <div className="text-center py-20 text-gray-400 dark:text-[#555]">
            <Building2 className="w-10 h-10 mx-auto mb-3 opacity-40" />
            <p className="text-sm">No tenants yet.</p>
            <Link
              href="/tenants/new"
              className="inline-block mt-3 text-sm text-blue-600 hover:text-blue-500"
            >
              Create your first tenant →
            </Link>
          </div>
        ) : (
          <div className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg overflow-hidden">
            {tenants.map((tenant, i) => (
              <Link
                key={tenant.id}
                href={`/tenants/${tenant.slug}`}
                className={`flex items-center justify-between px-4 py-4 hover:bg-gray-50 dark:hover:bg-[#1a1a1a] transition-colors group ${
                  i > 0 ? "border-t border-gray-100 dark:border-[#1e1e1e]" : ""
                }`}
              >
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-lg bg-blue-600/10 dark:bg-blue-600/20 flex items-center justify-center shrink-0">
                    <Building2 className="w-4 h-4 text-blue-600" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-gray-900 dark:text-white">
                      {tenant.name}
                    </p>
                    <p className="text-xs text-gray-400 dark:text-[#555] font-mono mt-0.5">
                      {tenant.namespace}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="hidden sm:flex items-center gap-4 text-xs text-gray-400 dark:text-[#555]">
                    <span>{tenant.cpu_limit} CPU</span>
                    <span>{tenant.memory_limit} RAM</span>
                    <span>{tenant.storage_limit}</span>
                  </div>
                  <Badge variant={tenant.active ? "success" : "secondary"}>
                    {tenant.active ? "active" : "inactive"}
                  </Badge>
                  <ArrowRight className="w-3.5 h-3.5 text-gray-400 dark:text-[#444] group-hover:text-gray-600 dark:group-hover:text-[#666] transition-colors" />
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
