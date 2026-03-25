"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";
import { useRouter, useParams } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { api } from "@/lib/api";
import { ArrowLeft, Loader2 } from "lucide-react";

function slugify(s: string) {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 63);
}

export default function NewAppPage() {
  const { data: session } = useSession();
  const router = useRouter();
  const params = useParams();
  const tenantSlug = params.slug as string;

  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugManual, setSlugManual] = useState(false);
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("main");
  const [replicas, setReplicas] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const accessToken = (session as typeof session & { accessToken?: string })?.accessToken;

  function handleNameChange(v: string) {
    setName(v);
    if (!slugManual) setSlug(slugify(v));
  }

  function handleSlugChange(v: string) {
    setSlugManual(true);
    setSlug(slugify(v));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !slug.trim() || !repoUrl.trim()) return;

    setLoading(true);
    setError("");
    try {
      await api.apps.create(
        tenantSlug,
        { slug, name, repo_url: repoUrl, branch, replicas },
        accessToken
      );
      router.push(`/tenants/${tenantSlug}/apps/${slug}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create application");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AppShell userEmail={session?.user?.email}>
      <div className="p-6 max-w-lg">
        {/* Header */}
        <div className="flex items-center gap-3 mb-8">
          <Link
            href={`/tenants/${tenantSlug}`}
            className="text-gray-400 dark:text-[#555] hover:text-gray-900 dark:hover:text-white transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div>
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
              New Application
            </h1>
            <p className="text-sm text-gray-500 dark:text-[#888] mt-0.5">
              Deploy a new app to{" "}
              <span className="font-mono text-gray-600 dark:text-[#aaa]">{tenantSlug}</span>
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg p-5 space-y-4">
            {/* Name */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-[#ccc] mb-1.5">
                Application name
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => handleNameChange(e.target.value)}
                placeholder="My App"
                required
                className="w-full px-3 py-2 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0f0f0f] text-gray-900 dark:text-white text-sm placeholder-gray-400 dark:placeholder-[#444] focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-colors"
              />
            </div>

            {/* Slug */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-[#ccc] mb-1.5">
                Slug{" "}
                <span className="text-gray-400 dark:text-[#555] font-normal">
                  (auto-generated)
                </span>
              </label>
              <input
                type="text"
                value={slug}
                onChange={(e) => handleSlugChange(e.target.value)}
                placeholder="my-app"
                required
                pattern="^[a-z0-9][a-z0-9-]*[a-z0-9]$"
                className="w-full px-3 py-2 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0f0f0f] text-gray-900 dark:text-white text-sm font-mono placeholder-gray-400 dark:placeholder-[#444] focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-colors"
              />
            </div>

            <div className="border-t border-gray-100 dark:border-[#1e1e1e] pt-4">
              <p className="text-xs font-medium text-gray-500 dark:text-[#777] uppercase tracking-wider mb-3">
                Repository
              </p>

              {/* Repo URL */}
              <div className="space-y-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-[#ccc] mb-1.5">
                    GitHub repository URL
                  </label>
                  <input
                    type="url"
                    value={repoUrl}
                    onChange={(e) => setRepoUrl(e.target.value)}
                    placeholder="https://github.com/owner/repo"
                    required
                    className="w-full px-3 py-2 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0f0f0f] text-gray-900 dark:text-white text-sm font-mono placeholder-gray-400 dark:placeholder-[#444] focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-colors"
                  />
                </div>

                {/* Branch */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-[#ccc] mb-1.5">
                    Branch
                  </label>
                  <input
                    type="text"
                    value={branch}
                    onChange={(e) => setBranch(e.target.value)}
                    placeholder="main"
                    required
                    className="w-full px-3 py-2 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0f0f0f] text-gray-900 dark:text-white text-sm font-mono placeholder-gray-400 dark:placeholder-[#444] focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-colors"
                  />
                </div>
              </div>
            </div>

            {/* Replicas */}
            <div className="border-t border-gray-100 dark:border-[#1e1e1e] pt-4">
              <label className="block text-sm font-medium text-gray-700 dark:text-[#ccc] mb-1.5">
                Replicas
              </label>
              <input
                type="number"
                min={1}
                max={20}
                value={replicas}
                onChange={(e) => setReplicas(Number(e.target.value))}
                className="w-24 px-3 py-2 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0f0f0f] text-gray-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-colors"
              />
              <p className="text-xs text-gray-400 dark:text-[#555] mt-1.5">
                Number of Kubernetes pod replicas.
              </p>
            </div>
          </div>

          {error && (
            <p className="text-sm text-red-500 bg-red-500/10 border border-red-500/20 rounded-md px-3 py-2">
              {error}
            </p>
          )}

          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={loading || !name.trim() || !slug.trim() || !repoUrl.trim()}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors"
            >
              {loading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              Create application
            </button>
            <Link
              href={`/tenants/${tenantSlug}`}
              className="px-4 py-2 rounded-md text-sm text-gray-500 dark:text-[#888] hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-[#1a1a1a] transition-colors"
            >
              Cancel
            </Link>
          </div>
        </form>
      </div>
    </AppShell>
  );
}
