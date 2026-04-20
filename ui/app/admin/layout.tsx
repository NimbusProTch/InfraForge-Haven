"use client";

import { useEffect } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { Loader2, ShieldAlert } from "lucide-react";

/**
 * /admin/* layout: gates every admin page on the `platform-admin`
 * Keycloak realm role.
 *
 * This is only a UI affordance — the backend re-checks the role on
 * every request (see `api/app/deps.py:require_platform_admin`). A user
 * who bypasses this client check hits a 403 from the API, so cluster
 * state is never at risk from a curious cookie. The goal here is just
 * to give non-admins a clear "you don't have access" surface instead
 * of a dead-end UI full of broken fetches.
 */
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { data: session, status } = useSession();
  const router = useRouter();

  const platformAdmin =
    (session as typeof session & { platformAdmin?: boolean })?.platformAdmin ?? false;

  useEffect(() => {
    if (status === "unauthenticated") router.push("/auth/signin");
  }, [status, router]);

  if (status === "loading") {
    return (
      <AppShell>
        <div className="flex items-center justify-center h-full min-h-[400px]">
          <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
        </div>
      </AppShell>
    );
  }

  if (status === "authenticated" && !platformAdmin) {
    return (
      <AppShell userEmail={session?.user?.email}>
        <div className="p-6 max-w-lg">
          <div
            className="bg-white dark:bg-[#141414] border border-amber-200 dark:border-amber-900/50 rounded-lg p-6 flex items-start gap-3"
            data-testid="admin-forbidden"
          >
            <ShieldAlert className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-gray-900 dark:text-white">
                Admin console is restricted to platform administrators.
              </p>
              <p className="text-sm text-gray-500 dark:text-zinc-400 mt-1">
                Your account does not have the <code>platform-admin</code> role.
                If you believe this is a mistake, contact the iyziops team.
              </p>
            </div>
          </div>
        </div>
      </AppShell>
    );
  }

  return <>{children}</>;
}
