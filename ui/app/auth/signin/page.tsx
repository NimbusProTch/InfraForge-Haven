"use client";

import { signIn, getProviders } from "next-auth/react";
import { Anchor, Github, Shield, Globe, Lock } from "lucide-react";
import { useEffect, useState } from "react";

interface Providers {
  keycloak?: { id: string; name: string };
  github?: { id: string; name: string };
}

export default function SignInPage() {
  const [providers, setProviders] = useState<Providers>({});

  useEffect(() => {
    getProviders().then((p) => {
      if (p) setProviders(p as unknown as Providers);
    });
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#09090b] relative overflow-hidden">
      {/* Subtle gradient background */}
      <div className="absolute inset-0 bg-gradient-to-br from-emerald-950/20 via-transparent to-teal-950/20" />
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[600px] bg-emerald-500/5 rounded-full blur-3xl" />

      <div className="relative z-10 w-full max-w-sm px-4">
        {/* Card */}
        <div className="bg-zinc-900/80 backdrop-blur-xl border border-zinc-800 rounded-2xl p-8 shadow-2xl shadow-emerald-500/5">
          {/* Logo */}
          <div className="flex flex-col items-center mb-8">
            <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center mb-4 shadow-lg shadow-emerald-500/20">
              <Anchor className="w-7 h-7 text-white" />
            </div>
            <h1 className="text-xl font-bold text-white tracking-tight">
              Haven Platform
            </h1>
            <p className="text-sm text-zinc-500 mt-1 text-center">
              EU-Sovereign PaaS for Dutch Municipalities
            </p>
          </div>

          <div className="space-y-3">
            {/* SSO / Keycloak — primary */}
            <button
              onClick={() => signIn("keycloak", { callbackUrl: "/dashboard" })}
              className="w-full inline-flex items-center justify-center gap-2.5 px-4 py-3 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-sm font-semibold transition-all shadow-lg shadow-emerald-500/20 hover:shadow-emerald-500/30"
            >
              <Lock className="w-4 h-4" />
              Sign in with SSO
            </button>

            {/* GitHub OAuth — secondary, optional */}
            {providers.github && (
              <>
                <div className="flex items-center gap-3 my-1">
                  <div className="flex-1 h-px bg-zinc-800" />
                  <span className="text-[10px] text-zinc-600 uppercase tracking-widest">or</span>
                  <div className="flex-1 h-px bg-zinc-800" />
                </div>
                <button
                  onClick={() => signIn("github", { callbackUrl: "/dashboard" })}
                  className="w-full inline-flex items-center justify-center gap-2.5 px-4 py-2.5 rounded-xl bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-zinc-300 hover:text-white text-sm font-medium transition-all"
                >
                  <Github className="w-4 h-4" />
                  Sign in with GitHub
                </button>
              </>
            )}
          </div>

          {/* Links */}
          <div className="flex items-center justify-center gap-4 mt-6">
            <button
              onClick={() => signIn("keycloak", { callbackUrl: "/dashboard" })}
              className="text-xs text-zinc-600 hover:text-emerald-400 transition-colors"
            >
              Forgot password?
            </button>
          </div>

          {/* Compliance footer */}
          <div className="mt-8 pt-5 border-t border-zinc-800/60">
            <div className="flex items-center justify-center gap-4">
              <div className="flex items-center gap-1.5">
                <Globe className="w-3 h-3 text-emerald-600" />
                <span className="text-[10px] text-zinc-600">EU Data Sovereignty</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Shield className="w-3 h-3 text-emerald-600" />
                <span className="text-[10px] text-zinc-600">VNG Haven Certified</span>
              </div>
            </div>
            <p className="text-center text-[10px] text-zinc-700 mt-2">
              GDPR Compliant · ISO 27001 · BIO Baseline
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
