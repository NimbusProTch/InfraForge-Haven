"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/components/Toast";
import { api } from "@/lib/api";
import {
  Plus,
  Loader2,
  Building2,
  Users,
  Trash2,
  X,
  FolderKanban,
} from "lucide-react";

interface Organization {
  id: string;
  slug: string;
  name: string;
  plan: string;
  tenant_count?: number;
  member_count?: number;
  created_at: string;
}

export default function OrganizationsPage() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const { error: toastError, success: toastSuccess } = useToast();
  const accessToken = (session as typeof session & { accessToken?: string })?.accessToken;

  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [newSlug, setNewSlug] = useState("");

  useEffect(() => {
    if (status === "unauthenticated") router.push("/auth/signin");
  }, [status, router]);

  const loadOrgs = useCallback(async () => {
    if (status !== "authenticated") return;
    try {
      const o = await api.organizations.list(accessToken);
      setOrgs(o as unknown as Organization[]);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [status, accessToken]);

  useEffect(() => {
    loadOrgs();
  }, [loadOrgs]);

  async function createOrg() {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const org = await api.organizations.create({
        name: newName,
        slug: newSlug || newName.toLowerCase().replace(/[^a-z0-9]/g, "-"),
      }, accessToken);
      setOrgs((prev) => [...prev, org as unknown as Organization]);
      toastSuccess(`Organization "${newName}" created`);
      setShowCreate(false);
      setNewName("");
      setNewSlug("");
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Failed to create organization");
    } finally {
      setCreating(false);
    }
  }

  async function deleteOrg(slug: string) {
    if (!confirm(`Delete organization "${slug}"? This cannot be undone.`)) return;
    setDeleting(slug);
    try {
      await api.organizations.delete(slug, accessToken);
      setOrgs((prev) => prev.filter((o) => o.slug !== slug));
      toastSuccess(`Organization "${slug}" deleted`);
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Failed to delete");
    } finally {
      setDeleting(null);
    }
  }

  if (status === "loading" || loading) {
    return (
      <AppShell userEmail={session?.user?.email}>
        <div className="flex items-center justify-center h-full min-h-[400px]">
          <Loader2 className="w-5 h-5 animate-spin text-zinc-600" />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell userEmail={session?.user?.email}>
      <div className="p-6 max-w-4xl">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-zinc-100">Organizations</h1>
            <p className="text-sm text-zinc-500 mt-1">Manage multi-tenant organizations with SSO and billing</p>
          </div>
          <button
            onClick={() => setShowCreate(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium transition-colors"
          >
            <Plus className="w-3 h-3" />
            New Organization
          </button>
        </div>

        {/* Create modal */}
        {showCreate && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl w-full max-w-md mx-4 shadow-2xl overflow-hidden">
              <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
                <div className="flex items-center gap-2">
                  <Building2 className="w-4 h-4 text-violet-500" />
                  <h2 className="text-sm font-semibold text-zinc-100">Create Organization</h2>
                </div>
                <button onClick={() => setShowCreate(false)} className="text-zinc-600 hover:text-zinc-300 transition-colors">
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="p-5 space-y-4">
                <div>
                  <label className="block text-xs font-medium text-zinc-400 mb-1.5">Name</label>
                  <input
                    type="text"
                    value={newName}
                    onChange={(e) => {
                      setNewName(e.target.value);
                      setNewSlug(e.target.value.toLowerCase().replace(/[^a-z0-9]/g, "-"));
                    }}
                    placeholder="Gemeente Amsterdam"
                    className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-800 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-violet-600 focus:ring-1 focus:ring-violet-600/30"
                    autoFocus
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-zinc-400 mb-1.5">Slug</label>
                  <input
                    type="text"
                    value={newSlug}
                    onChange={(e) => setNewSlug(e.target.value)}
                    placeholder="gemeente-amsterdam"
                    className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-800 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-violet-600 focus:ring-1 focus:ring-violet-600/30 font-mono"
                  />
                </div>
                <div className="flex justify-end gap-2 pt-2">
                  <button onClick={() => setShowCreate(false)} className="px-3 py-1.5 rounded-lg text-xs font-medium text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 transition-colors">
                    Cancel
                  </button>
                  <button
                    onClick={createOrg}
                    disabled={!newName.trim() || creating}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-violet-600 hover:bg-violet-700 text-white text-xs font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {creating && <Loader2 className="w-3 h-3 animate-spin" />}
                    Create
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Org list */}
        {orgs.length === 0 ? (
          <div className="text-center py-16 border border-dashed border-zinc-800 rounded-xl">
            <Building2 className="w-8 h-8 mx-auto mb-2 text-zinc-700" />
            <p className="text-sm text-zinc-500">No organizations yet.</p>
            <p className="text-xs text-zinc-600 mt-1">Create an organization to group tenants and manage SSO.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {orgs.map((org) => (
              <div
                key={org.id}
                className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-4 hover:border-zinc-700 transition-colors"
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-violet-500/10 border border-violet-500/20 flex items-center justify-center">
                      <Building2 className="w-5 h-5 text-violet-400" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm font-semibold text-zinc-200">{org.name}</h3>
                        <Badge variant="secondary">{org.plan ?? "free"}</Badge>
                      </div>
                      <div className="flex items-center gap-3 mt-1 text-xs text-zinc-600">
                        <span className="font-mono">{org.slug}</span>
                        {org.tenant_count !== undefined && (
                          <span className="flex items-center gap-1">
                            <FolderKanban className="w-3 h-3" />
                            {org.tenant_count} project{org.tenant_count !== 1 ? "s" : ""}
                          </span>
                        )}
                        {org.member_count !== undefined && (
                          <span className="flex items-center gap-1">
                            <Users className="w-3 h-3" />
                            {org.member_count} member{org.member_count !== 1 ? "s" : ""}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={() => deleteOrg(org.slug)}
                    disabled={deleting === org.slug}
                    className="text-zinc-700 hover:text-red-400 transition-colors disabled:opacity-50"
                  >
                    {deleting === org.slug ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Trash2 className="w-4 h-4" />
                    )}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
