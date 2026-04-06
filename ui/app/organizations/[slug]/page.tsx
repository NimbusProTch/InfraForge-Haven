"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { useRouter, useParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/Toast";
import { api } from "@/lib/api";
import {
  Building2,
  Users,
  FolderKanban,
  Shield,
  CreditCard,
  Loader2,
  Plus,
  Trash2,
  X,
  ChevronLeft,
  UserPlus,
  Link2,
  Unlink,
} from "lucide-react";

interface Organization {
  id: string;
  slug: string;
  name: string;
  plan: string;
  active: boolean;
  created_at: string;
}

interface OrgMember {
  id: string;
  organization_id: string;
  user_id: string;
  email: string;
  display_name: string | null;
  role: string;
  created_at: string;
}

interface OrgTenant {
  id: string;
  organization_id: string;
  tenant_id: string;
  created_at: string;
}

interface Tenant {
  id: string;
  slug: string;
  name: string;
  tier: string;
  active: boolean;
}

interface BillingSummary {
  organization_id: string;
  organization_slug: string;
  plan: string;
  tenant_count: number;
  stripe_customer_id: string | null;
  stripe_subscription_id: string | null;
}

export default function OrganizationDetailPage() {
  const { slug } = useParams<{ slug: string }>();
  const { data: session, status } = useSession();
  const router = useRouter();
  const { error: toastError, success: toastSuccess } = useToast();
  const accessToken = (session as typeof session & { accessToken?: string })?.accessToken;

  const [org, setOrg] = useState<Organization | null>(null);
  const [members, setMembers] = useState<OrgMember[]>([]);
  const [orgTenants, setOrgTenants] = useState<OrgTenant[]>([]);
  const [allTenants, setAllTenants] = useState<Tenant[]>([]);
  const [billing, setBilling] = useState<BillingSummary | null>(null);
  const [loading, setLoading] = useState(true);

  // Invite member state
  const [showInvite, setShowInvite] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteUserId, setInviteUserId] = useState("");
  const [inviteRole, setInviteRole] = useState("member");
  const [inviting, setInviting] = useState(false);

  // Add tenant state
  const [showAddTenant, setShowAddTenant] = useState(false);
  const [selectedTenantId, setSelectedTenantId] = useState("");
  const [addingTenant, setAddingTenant] = useState(false);

  // Confirmation modal state
  const [confirmAction, setConfirmAction] = useState<{
    title: string;
    message: string;
    destructive?: boolean;
    onConfirm: () => void;
  } | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);

  useEffect(() => {
    if (status === "unauthenticated") router.push("/auth/signin");
  }, [status, router]);

  const loadData = useCallback(async () => {
    if (status !== "authenticated" || !slug) return;
    setLoading(true);
    try {
      const [o, m, t, b, tenants] = await Promise.all([
        api.organizations.get(slug, accessToken),
        api.organizations.listMembers(slug, accessToken).catch(() => []),
        api.organizations.listTenants(slug, accessToken).catch(() => []),
        api.organizations.billingSummary(slug, accessToken).catch(() => null),
        api.tenants.list(accessToken).catch(() => []),
      ]);
      setOrg(o as unknown as Organization);
      setMembers(m as unknown as OrgMember[]);
      setOrgTenants(t as unknown as OrgTenant[]);
      setBilling(b as unknown as BillingSummary | null);
      setAllTenants(tenants as unknown as Tenant[]);
    } catch {
      toastError("Failed to load organization");
      router.push("/organizations");
    } finally {
      setLoading(false);
    }
  }, [status, slug, accessToken, router, toastError]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // ── Member actions ──

  async function handleInvite() {
    if (!inviteEmail.trim() || !inviteUserId.trim()) return;
    setInviting(true);
    try {
      await api.organizations.addMember(slug, {
        user_id: inviteUserId,
        email: inviteEmail,
        role: inviteRole,
      }, accessToken);
      toastSuccess(`Invited ${inviteEmail}`);
      setShowInvite(false);
      setInviteEmail("");
      setInviteUserId("");
      setInviteRole("member");
      loadData();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Failed to invite");
    } finally {
      setInviting(false);
    }
  }

  async function handleChangeRole(userId: string, newRole: string) {
    try {
      await api.organizations.updateMember(slug, userId, { role: newRole }, accessToken);
      toastSuccess("Role updated");
      loadData();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Failed to update role");
    }
  }

  function handleRemoveMember(userId: string, email: string) {
    setConfirmAction({
      title: "Remove Member",
      message: `Are you sure you want to remove ${email} from this organization? They will lose access to all organization resources.`,
      destructive: true,
      onConfirm: async () => {
        setConfirmLoading(true);
        try {
          await api.organizations.removeMember(slug, userId, accessToken);
          toastSuccess(`Removed ${email}`);
          setConfirmAction(null);
          loadData();
        } catch (err) {
          toastError(err instanceof Error ? err.message : "Failed to remove member");
        } finally {
          setConfirmLoading(false);
        }
      },
    });
  }

  // ── Tenant actions ──

  async function handleAddTenant() {
    if (!selectedTenantId) return;
    setAddingTenant(true);
    try {
      await api.organizations.bindTenant(slug, { tenant_id: selectedTenantId }, accessToken);
      toastSuccess("Project added to organization");
      setShowAddTenant(false);
      setSelectedTenantId("");
      loadData();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Failed to add project");
    } finally {
      setAddingTenant(false);
    }
  }

  function handleRemoveTenant(tenantId: string, tenantName: string) {
    setConfirmAction({
      title: "Remove Project",
      message: `Remove "${tenantName}" from this organization? The project will still exist but won't be managed under this organization.`,
      destructive: true,
      onConfirm: async () => {
        setConfirmLoading(true);
        try {
          await api.organizations.unbindTenant(slug, tenantId, accessToken);
          toastSuccess("Project removed from organization");
          setConfirmAction(null);
          loadData();
        } catch (err) {
          toastError(err instanceof Error ? err.message : "Failed to remove project");
        } finally {
          setConfirmLoading(false);
        }
      },
    });
  }

  // ── Derived ──

  const boundTenantIds = new Set(orgTenants.map((t) => t.tenant_id));
  const unboundTenants = allTenants.filter((t) => !boundTenantIds.has(t.id));
  const boundTenantDetails = orgTenants.map((ot) => ({
    ...ot,
    tenant: allTenants.find((t) => t.id === ot.tenant_id),
  }));

  const roleColor = (role: string) => {
    switch (role) {
      case "owner": return "bg-violet-100 text-violet-700 dark:bg-violet-500/20 dark:text-violet-400";
      case "admin": return "bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-400";
      case "billing": return "bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-400";
      default: return "bg-gray-100 text-gray-700 dark:bg-zinc-700 dark:text-zinc-300";
    }
  };

  if (status === "loading" || loading) {
    return (
      <AppShell userEmail={session?.user?.email}>
        <div className="flex items-center justify-center h-full min-h-[400px]">
          <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
        </div>
      </AppShell>
    );
  }

  if (!org) return null;

  return (
    <AppShell userEmail={session?.user?.email}>
      <div className="p-6 max-w-4xl">
        {/* Header */}
        <button onClick={() => router.push("/organizations")} className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 dark:text-zinc-600 dark:hover:text-zinc-400 mb-4 transition-colors">
          <ChevronLeft className="w-3 h-3" /> Organizations
        </button>

        <div className="flex items-center gap-4 mb-6">
          <div className="w-12 h-12 rounded-xl bg-violet-500/10 border border-violet-500/20 flex items-center justify-center">
            <Building2 className="w-6 h-6 text-violet-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900 dark:text-zinc-100">{org.name}</h1>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-xs font-mono text-gray-400 dark:text-zinc-600">{org.slug}</span>
              <Badge variant="secondary">{org.plan}</Badge>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <Tabs defaultValue="projects">
          <TabsList>
            <TabsTrigger value="projects">
              <FolderKanban className="w-3.5 h-3.5 mr-1" /> Projects
              <span className="ml-1 text-xs text-gray-400">{orgTenants.length}</span>
            </TabsTrigger>
            <TabsTrigger value="members">
              <Users className="w-3.5 h-3.5 mr-1" /> Members
              <span className="ml-1 text-xs text-gray-400">{members.length}</span>
            </TabsTrigger>
            <TabsTrigger value="sso">
              <Shield className="w-3.5 h-3.5 mr-1" /> SSO
            </TabsTrigger>
            <TabsTrigger value="billing">
              <CreditCard className="w-3.5 h-3.5 mr-1" /> Billing
            </TabsTrigger>
          </TabsList>

          {/* ── Projects Tab ── */}
          <TabsContent value="projects" className="mt-4 space-y-3">
            <div className="flex justify-end">
              <button
                onClick={() => setShowAddTenant(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium transition-colors"
              >
                <Plus className="w-3 h-3" /> Add Project
              </button>
            </div>

            {boundTenantDetails.length === 0 ? (
              <div className="text-center py-10 border border-dashed border-gray-200 dark:border-zinc-800 rounded-xl">
                <FolderKanban className="w-6 h-6 mx-auto mb-2 text-gray-400 dark:text-zinc-700" />
                <p className="text-sm text-gray-500 dark:text-zinc-500">No projects in this organization yet.</p>
              </div>
            ) : (
              boundTenantDetails.map((item) => (
                <div
                  key={item.id}
                  className="flex items-center justify-between p-3 rounded-lg border border-gray-200 dark:border-zinc-800 bg-white dark:bg-zinc-900/50"
                >
                  <div className="flex items-center gap-3">
                    <Link2 className="w-4 h-4 text-blue-400" />
                    <div>
                      <p className="text-sm font-medium text-gray-900 dark:text-zinc-200">
                        {item.tenant?.name || item.tenant_id}
                      </p>
                      <p className="text-xs text-gray-400 dark:text-zinc-600 font-mono">
                        {item.tenant?.slug || item.tenant_id.slice(0, 8)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {item.tenant && <Badge variant="secondary">{item.tenant.tier}</Badge>}
                    <button
                      onClick={(e) => { e.stopPropagation(); handleRemoveTenant(item.tenant_id, item.tenant?.name || item.tenant_id); }}
                      className="p-1.5 rounded-md text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                      title="Remove from organization"
                    >
                      <Unlink className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))
            )}

            {/* Add tenant modal */}
            {showAddTenant && (
              <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
                <div className="bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-800 rounded-xl w-full max-w-md mx-4 shadow-2xl">
                  <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-zinc-800">
                    <h2 className="text-sm font-semibold text-gray-900 dark:text-zinc-100">Add Project to Organization</h2>
                    <button onClick={() => setShowAddTenant(false)} className="text-gray-400 hover:text-gray-700 dark:hover:text-zinc-300">
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                  <div className="p-5 space-y-4">
                    {unboundTenants.length === 0 && allTenants.length === 0 ? (
                      <div className="text-center py-4">
                        <p className="text-sm text-gray-500 dark:text-zinc-500 mb-3">You don&apos;t have any projects yet.</p>
                        <button
                          onClick={() => { setShowAddTenant(false); router.push("/tenants"); }}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium transition-colors"
                        >
                          <Plus className="w-3 h-3" /> Create Project
                        </button>
                      </div>
                    ) : unboundTenants.length === 0 ? (
                      <p className="text-sm text-gray-500 dark:text-zinc-500">All your projects are already in this organization.</p>
                    ) : (
                      <div>
                        <label className="block text-xs font-medium text-gray-500 dark:text-zinc-400 mb-1.5">Select Project</label>
                        <select
                          value={selectedTenantId}
                          onChange={(e) => setSelectedTenantId(e.target.value)}
                          className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-zinc-700 bg-gray-100 dark:bg-zinc-800 text-sm text-gray-900 dark:text-zinc-100"
                        >
                          <option value="">Choose a project...</option>
                          {unboundTenants.map((t) => (
                            <option key={t.id} value={t.id}>{t.name} ({t.slug})</option>
                          ))}
                        </select>
                      </div>
                    )}
                    <div className="flex justify-end gap-2">
                      <button onClick={() => setShowAddTenant(false)} className="px-3 py-1.5 rounded-lg text-xs text-gray-500 hover:text-gray-900 transition-colors">Cancel</button>
                      <button
                        onClick={handleAddTenant}
                        disabled={!selectedTenantId || addingTenant}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium disabled:opacity-40 transition-colors"
                      >
                        {addingTenant && <Loader2 className="w-3 h-3 animate-spin" />}
                        Add
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </TabsContent>

          {/* ── Members Tab ── */}
          <TabsContent value="members" className="mt-4 space-y-3">
            <div className="flex justify-end">
              <button
                onClick={() => setShowInvite(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-violet-600 hover:bg-violet-700 text-white text-xs font-medium transition-colors"
              >
                <UserPlus className="w-3 h-3" /> Invite Member
              </button>
            </div>

            {members.map((m) => (
              <div key={m.id} className="flex items-center justify-between p-3 rounded-lg border border-gray-200 dark:border-zinc-800 bg-white dark:bg-zinc-900/50">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-gray-200 dark:bg-zinc-700 flex items-center justify-center text-xs font-bold text-gray-600 dark:text-zinc-300">
                    {(m.display_name || m.email).charAt(0).toUpperCase()}
                  </div>
                  <div>
                    <p className="text-sm font-medium text-gray-900 dark:text-zinc-200">{m.display_name || m.email}</p>
                    <p className="text-xs text-gray-400 dark:text-zinc-600">{m.email}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <select
                    value={m.role}
                    onChange={(e) => handleChangeRole(m.user_id, e.target.value)}
                    className={`text-xs font-medium px-2 py-1 rounded-md border-0 ${roleColor(m.role)} cursor-pointer`}
                  >
                    <option value="owner">Owner</option>
                    <option value="admin">Admin</option>
                    <option value="member">Member</option>
                    <option value="billing">Billing</option>
                  </select>
                  <button
                    onClick={() => handleRemoveMember(m.user_id, m.email)}
                    className="p-1.5 rounded-md text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                    title="Remove member"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            ))}

            {/* Invite modal */}
            {showInvite && (
              <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
                <div className="bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-800 rounded-xl w-full max-w-md mx-4 shadow-2xl">
                  <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-zinc-800">
                    <h2 className="text-sm font-semibold text-gray-900 dark:text-zinc-100">Invite Member</h2>
                    <button onClick={() => setShowInvite(false)} className="text-gray-400 hover:text-gray-700 dark:hover:text-zinc-300">
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                  <div className="p-5 space-y-4">
                    <div>
                      <label className="block text-xs font-medium text-gray-500 dark:text-zinc-400 mb-1.5">User ID (Keycloak sub)</label>
                      <input
                        type="text"
                        value={inviteUserId}
                        onChange={(e) => setInviteUserId(e.target.value)}
                        placeholder="keycloak-user-id"
                        className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-zinc-700 bg-gray-100 dark:bg-zinc-800 text-sm font-mono"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-500 dark:text-zinc-400 mb-1.5">Email</label>
                      <input
                        type="email"
                        value={inviteEmail}
                        onChange={(e) => setInviteEmail(e.target.value)}
                        placeholder="user@gemeente.nl"
                        className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-zinc-700 bg-gray-100 dark:bg-zinc-800 text-sm"
                        autoFocus
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-500 dark:text-zinc-400 mb-1.5">Role</label>
                      <select
                        value={inviteRole}
                        onChange={(e) => setInviteRole(e.target.value)}
                        className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-zinc-700 bg-gray-100 dark:bg-zinc-800 text-sm"
                      >
                        <option value="member">Member</option>
                        <option value="admin">Admin</option>
                        <option value="billing">Billing</option>
                      </select>
                    </div>
                    <div className="flex justify-end gap-2 pt-2">
                      <button onClick={() => setShowInvite(false)} className="px-3 py-1.5 rounded-lg text-xs text-gray-500 hover:text-gray-900 transition-colors">Cancel</button>
                      <button
                        onClick={handleInvite}
                        disabled={!inviteEmail.trim() || !inviteUserId.trim() || inviting}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-violet-600 hover:bg-violet-700 text-white text-xs font-medium disabled:opacity-40 transition-colors"
                      >
                        {inviting && <Loader2 className="w-3 h-3 animate-spin" />}
                        Invite
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </TabsContent>

          {/* ── SSO Tab ── */}
          <TabsContent value="sso" className="mt-4">
            <div className="text-center py-12 border border-dashed border-gray-200 dark:border-zinc-800 rounded-xl">
              <Shield className="w-8 h-8 mx-auto mb-3 text-gray-400 dark:text-zinc-700" />
              <p className="text-sm font-medium text-gray-600 dark:text-zinc-400">SSO Configuration</p>
              <p className="text-xs text-gray-400 dark:text-zinc-600 mt-1 max-w-sm mx-auto">
                Configure SAML 2.0 or OIDC identity provider for your organization.
                Members will authenticate through your corporate IdP via Keycloak federation.
              </p>
              <Badge variant="secondary" className="mt-3">Coming Soon</Badge>
            </div>
          </TabsContent>

          {/* ── Billing Tab ── */}
          <TabsContent value="billing" className="mt-4">
            {billing ? (
              <div className="space-y-4">
                <div className="grid grid-cols-3 gap-4">
                  <div className="p-4 rounded-lg border border-gray-200 dark:border-zinc-800 bg-white dark:bg-zinc-900/50">
                    <p className="text-xs text-gray-400 dark:text-zinc-600 mb-1">Plan</p>
                    <p className="text-lg font-bold text-gray-900 dark:text-zinc-100 capitalize">{billing.plan}</p>
                  </div>
                  <div className="p-4 rounded-lg border border-gray-200 dark:border-zinc-800 bg-white dark:bg-zinc-900/50">
                    <p className="text-xs text-gray-400 dark:text-zinc-600 mb-1">Projects</p>
                    <p className="text-lg font-bold text-gray-900 dark:text-zinc-100">{billing.tenant_count}</p>
                  </div>
                  <div className="p-4 rounded-lg border border-gray-200 dark:border-zinc-800 bg-white dark:bg-zinc-900/50">
                    <p className="text-xs text-gray-400 dark:text-zinc-600 mb-1">Members</p>
                    <p className="text-lg font-bold text-gray-900 dark:text-zinc-100">{members.length}</p>
                  </div>
                </div>
                <div className="p-4 rounded-lg border border-gray-200 dark:border-zinc-800 bg-white dark:bg-zinc-900/50">
                  <p className="text-xs text-gray-400 dark:text-zinc-600 mb-2">Payment</p>
                  {billing.stripe_customer_id ? (
                    <p className="text-sm text-gray-700 dark:text-zinc-300">Stripe Customer: {billing.stripe_customer_id}</p>
                  ) : (
                    <p className="text-sm text-gray-400 dark:text-zinc-600">No payment method configured. Stripe integration coming soon.</p>
                  )}
                </div>
              </div>
            ) : (
              <div className="text-center py-10 border border-dashed border-gray-200 dark:border-zinc-800 rounded-xl">
                <CreditCard className="w-6 h-6 mx-auto mb-2 text-gray-400 dark:text-zinc-700" />
                <p className="text-sm text-gray-500 dark:text-zinc-500">Billing data unavailable</p>
              </div>
            )}
          </TabsContent>
        </Tabs>

        {/* Confirmation Modal */}
        {confirmAction && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
            <div className="bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-800 rounded-xl w-full max-w-sm mx-4 shadow-2xl overflow-hidden">
              <div className="px-5 py-4 border-b border-gray-200 dark:border-zinc-800">
                <h2 className="text-sm font-semibold text-gray-900 dark:text-zinc-100">{confirmAction.title}</h2>
              </div>
              <div className="p-5">
                <p className="text-sm text-gray-600 dark:text-zinc-400 leading-relaxed">{confirmAction.message}</p>
              </div>
              <div className="flex justify-end gap-2 px-5 py-3 bg-gray-50 dark:bg-zinc-800/50 border-t border-gray-200 dark:border-zinc-800">
                <button
                  onClick={() => setConfirmAction(null)}
                  disabled={confirmLoading}
                  className="px-4 py-2 rounded-lg text-sm font-medium text-gray-600 dark:text-zinc-400 hover:bg-gray-100 dark:hover:bg-zinc-700 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={confirmAction.onConfirm}
                  disabled={confirmLoading}
                  className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium text-white transition-colors disabled:opacity-50 ${
                    confirmAction.destructive
                      ? "bg-red-600 hover:bg-red-700"
                      : "bg-blue-600 hover:bg-blue-700"
                  }`}
                >
                  {confirmLoading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  Confirm
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
