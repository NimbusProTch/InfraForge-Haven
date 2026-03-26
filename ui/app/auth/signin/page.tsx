"use client";

import { signIn, getProviders } from "next-auth/react";
import { Anchor, Github } from "lucide-react";
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
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-[#0a0a0a]">
      <div className="w-full max-w-sm">
        {/* Card */}
        <div className="bg-white dark:bg-[#111] border border-gray-200 dark:border-[#222] rounded-xl p-8 shadow-sm">
          {/* Logo */}
          <div className="flex flex-col items-center mb-8">
            <div className="w-12 h-12 rounded-xl bg-blue-600 flex items-center justify-center mb-4">
              <Anchor className="w-6 h-6 text-white" />
            </div>
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">Haven Platform</h1>
            <p className="text-sm text-gray-500 dark:text-[#888] mt-1">
              Haven-Compliant PaaS for NL municipalities
            </p>
          </div>

          <div className="space-y-3">
            {/* Keycloak */}
            <button
              onClick={() => signIn("keycloak", { callbackUrl: "/dashboard" })}
              className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium transition-colors"
            >
              Sign in with Keycloak
            </button>

            {/* GitHub OAuth — only shown when provider is configured */}
            {providers.github && (
              <button
                onClick={() => signIn("github", { callbackUrl: "/dashboard" })}
                className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-gray-900 hover:bg-gray-800 dark:bg-[#1a1a1a] dark:hover:bg-[#222] border border-gray-700 dark:border-[#333] text-white text-sm font-medium transition-colors"
              >
                <Github className="w-4 h-4" />
                Sign in with GitHub
              </button>
            )}
          </div>

          <p className="text-center text-xs text-gray-400 dark:text-[#555] mt-6">
            EU data sovereignty · VNG Haven certified
          </p>
        </div>
      </div>
    </div>
  );
}
