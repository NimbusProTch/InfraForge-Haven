"use client";

import { signIn, getProviders } from "next-auth/react";
import { Anchor, Github, Shield, Globe, Lock, AlertCircle } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

interface Providers {
  keycloak?: { id: string; name: string };
  github?: { id: string; name: string };
}

// P10 (Sprint H2 #25): the middleware redirects here with `?reason=`
// when a token-refresh failure invalidates the session. We surface the
// reason as a banner so the user understands why they're being asked to
// log in again instead of just bouncing them silently.
function SessionExpiredBanner() {
  const params = useSearchParams();
  const reason = params.get("reason");

  if (!reason) return null;

  const message =
    reason === "session_expired"
      ? "Your session has expired. Please sign in again."
      : reason === "session_error"
        ? "We couldn't refresh your session. Please sign in again."
        : null;

  if (!message) return null;

  return (
    <div className="mb-4 flex items-start gap-2.5 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-700/50 dark:bg-amber-950/40 dark:text-amber-300">
      <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
      <span>{message}</span>
    </div>
  );
}

function SignInInner() {
  const [providers, setProviders] = useState<Providers>({});
  const params = useSearchParams();
  // After successful signin, return the user to the page they were
  // trying to view when the middleware redirected them. The middleware
  // sets `callbackUrl` alongside `reason`.
  const callbackUrl = params.get("callbackUrl") || "/dashboard";

  useEffect(() => {
    getProviders().then((p) => {
      if (p) setProviders(p as unknown as Providers);
    });
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-[#09090b] relative overflow-hidden">
      {/* Subtle gradient background */}
      <div className="absolute inset-0 bg-gradient-to-br from-emerald-950/20 via-transparent to-teal-950/20" />
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[600px] bg-emerald-500/5 rounded-full blur-3xl" />

      <div className="relative z-10 w-full max-w-sm px-4">
        {/* Card */}
        <div className="bg-white dark:bg-zinc-900/80 backdrop-blur-xl border border-gray-200 dark:border-zinc-800 rounded-2xl p-8 shadow-2xl shadow-emerald-500/5">
          {/* Logo */}
          <div className="flex flex-col items-center mb-8">
            <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center mb-4 shadow-lg shadow-emerald-500/20">
              <Anchor className="w-7 h-7 text-white" />
            </div>
            <h1 className="text-xl font-bold text-gray-900 dark:text-white tracking-tight">
              Haven Platform
            </h1>
            <p className="text-sm text-gray-500 dark:text-zinc-500 mt-1 text-center">
              EU-Sovereign PaaS for Dutch Municipalities
            </p>
          </div>

          {/* P10: surface session-expired reason from middleware */}
          <SessionExpiredBanner />

          <div className="space-y-3">
            {/* SSO / Keycloak — primary */}
            <button
              onClick={() => signIn("keycloak", { callbackUrl })}
              className="w-full inline-flex items-center justify-center gap-2.5 px-4 py-3 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-sm font-semibold transition-all shadow-lg shadow-emerald-500/20 hover:shadow-emerald-500/30"
            >
              <Lock className="w-4 h-4" />
              Sign in with SSO
            </button>

            {/* GitHub OAuth — secondary, optional */}
            {providers.github && (
              <>
                <div className="flex items-center gap-3 my-1">
                  <div className="flex-1 h-px bg-gray-200 dark:bg-zinc-800" />
                  <span className="text-xs text-gray-400 dark:text-zinc-600 uppercase tracking-widest">or</span>
                  <div className="flex-1 h-px bg-gray-200 dark:bg-zinc-800" />
                </div>
                <button
                  onClick={() => signIn("github", { callbackUrl })}
                  className="w-full inline-flex items-center justify-center gap-2.5 px-4 py-2.5 rounded-xl bg-gray-100 dark:bg-zinc-800 hover:bg-gray-200 dark:hover:bg-zinc-700 border border-gray-300 dark:border-zinc-700 text-gray-700 dark:text-zinc-300 hover:text-gray-900 dark:hover:text-white text-sm font-medium transition-all"
                >
                  <Github className="w-4 h-4" />
                  Sign in with GitHub
                </button>
              </>
            )}
          </div>

          {/* Links */}
          <div className="flex items-center justify-center gap-4 mt-6">
            <a
              href={`${process.env.NEXT_PUBLIC_KEYCLOAK_URL ?? "https://keycloak.iyziops.com"}/realms/${process.env.NEXT_PUBLIC_KEYCLOAK_REALM ?? "haven"}/login-actions/reset-credentials`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-gray-400 dark:text-zinc-600 hover:text-emerald-400 transition-colors"
            >
              Forgot password?
            </a>
          </div>

          {/* Compliance footer */}
          <div className="mt-8 pt-5 border-t border-gray-100 dark:border-zinc-800/60">
            <div className="flex items-center justify-center gap-4">
              <div className="flex items-center gap-1.5">
                <Globe className="w-3 h-3 text-emerald-600" />
                <span className="text-xs text-gray-400 dark:text-zinc-600">EU Data Sovereignty</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Shield className="w-3 h-3 text-emerald-600" />
                <span className="text-xs text-gray-400 dark:text-zinc-600">VNG Haven Certified</span>
              </div>
            </div>
            <p className="text-center text-xs text-gray-400 dark:text-zinc-700 mt-2">
              GDPR Compliant · Haven 12/15 Infrastructure
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// useSearchParams() requires a Suspense boundary in Next.js 14 App Router.
export default function SignInPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-[#09090b]">
          <div className="animate-pulse text-gray-400">Loading…</div>
        </div>
      }
    >
      <SignInInner />
    </Suspense>
  );
}
