import Link from "next/link";
import { redirect } from "next/navigation";
import { getServerSession } from "next-auth";
import { ArrowRight, Shield, Globe, Zap, Lock, Activity } from "lucide-react";

import { authOptions } from "@/lib/auth";

/**
 * Public landing page for unauthenticated visitors.
 *
 * Enterprise-only positioning (plan file: peki-idmi-unu-bi-joyful-newt.md):
 *   - No self-signup — prospective customers use "Request access"
 *   - Authenticated users skip straight to /dashboard
 *   - No VNG-Haven-specific compliance badges (those live on a separate
 *     /compliance page for prospects who ask)
 */
export default async function Home() {
  const session = await getServerSession(authOptions);
  if (session) {
    redirect("/dashboard");
  }

  return (
    <div className="min-h-screen flex flex-col bg-gradient-to-br from-slate-50 via-white to-indigo-50 dark:from-zinc-950 dark:via-zinc-900 dark:to-indigo-950/30">
      {/* Top bar */}
      <header className="px-6 md:px-12 py-5 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-500 via-indigo-500 to-violet-600 flex items-center justify-center shadow-md shadow-indigo-500/30">
            <span className="font-extrabold text-sm text-white leading-none tracking-tighter">
              iy
            </span>
          </div>
          <span className="text-lg font-bold text-gray-900 dark:text-white tracking-tight">
            iyziops
          </span>
        </Link>
        <nav className="flex items-center gap-3">
          <Link
            href="/auth/signin"
            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-zinc-300 hover:text-gray-900 dark:hover:text-white transition-colors"
          >
            Sign in
          </Link>
          <Link
            href="/auth/request-access"
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-gray-900 dark:bg-white text-white dark:text-gray-900 text-sm font-semibold hover:bg-gray-800 dark:hover:bg-zinc-100 transition-colors"
          >
            Request access <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </nav>
      </header>

      {/* Hero */}
      <main className="flex-1 flex items-center">
        <div className="w-full max-w-5xl mx-auto px-6 md:px-12 py-16 md:py-24">
          <div className="max-w-3xl">
            <p className="text-sm font-medium text-indigo-600 dark:text-indigo-400 mb-4 tracking-wide">
              Enterprise DevOps platform
            </p>
            <h1 className="text-4xl md:text-6xl font-extrabold text-gray-900 dark:text-white tracking-tight leading-[1.1]">
              Ship software with the control your team expects.
            </h1>
            <p className="mt-6 text-lg text-gray-600 dark:text-zinc-400 leading-relaxed max-w-2xl">
              iyziops gives engineering teams a self-service
              Kubernetes platform with managed databases, per-tenant
              isolation, and EU data sovereignty — delivered as a
              provisioned service on infrastructure you can audit.
            </p>
            <div className="mt-10 flex flex-wrap items-center gap-3">
              <Link
                href="/auth/request-access"
                className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white text-sm font-semibold shadow-lg shadow-indigo-500/30 transition-all"
              >
                Request access
                <ArrowRight className="w-4 h-4" />
              </Link>
              <Link
                href="/auth/signin"
                className="inline-flex items-center gap-2 px-6 py-3 rounded-xl border border-gray-300 dark:border-zinc-700 text-gray-900 dark:text-white text-sm font-semibold hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors"
              >
                <Lock className="w-4 h-4" />
                Sign in
              </Link>
            </div>
          </div>

          {/* Feature grid */}
          <div className="mt-20 grid grid-cols-1 md:grid-cols-3 gap-6">
            <Feature
              icon={<Zap className="w-5 h-5" />}
              title="Self-service deploys"
              body="Connect a repo, get a URL. Builds, databases, secrets, and rollbacks — all wired by default."
            />
            <Feature
              icon={<Shield className="w-5 h-5" />}
              title="Per-tenant isolation"
              body="Kubernetes namespaces, network policies, resource quotas, and separate credentials for every project."
            />
            <Feature
              icon={<Globe className="w-5 h-5" />}
              title="EU data sovereignty"
              body="Runs on Hetzner and Cyso infrastructure inside the EU. GDPR-aligned by default, audit log included."
            />
          </div>
        </div>
      </main>

      {/* Foot */}
      <footer className="px-6 md:px-12 py-6 border-t border-gray-200 dark:border-zinc-800/60 flex items-center justify-between text-xs text-gray-500 dark:text-zinc-500">
        <div className="flex items-center gap-2">
          <Activity className="w-3 h-3" />
          <span>iyziops — enterprise DevOps platform</span>
        </div>
        <div className="flex items-center gap-4">
          <Link href="/auth/request-access" className="hover:text-gray-900 dark:hover:text-zinc-200">
            Request access
          </Link>
          <Link href="/auth/signin" className="hover:text-gray-900 dark:hover:text-zinc-200">
            Sign in
          </Link>
        </div>
      </footer>
    </div>
  );
}

function Feature({
  icon,
  title,
  body,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
}) {
  return (
    <div className="rounded-2xl border border-gray-200 dark:border-zinc-800 bg-white/70 dark:bg-zinc-900/50 backdrop-blur-sm p-6 shadow-sm">
      <div className="w-10 h-10 rounded-lg bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400 flex items-center justify-center mb-4">
        {icon}
      </div>
      <h3 className="text-base font-semibold text-gray-900 dark:text-white mb-1.5">
        {title}
      </h3>
      <p className="text-sm text-gray-600 dark:text-zinc-400 leading-relaxed">{body}</p>
    </div>
  );
}
