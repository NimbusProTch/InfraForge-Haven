"use client";

import { useEffect, useState, useCallback } from "react";
import { api, type TenantMember } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { Badge } from "@/components/ui/badge";
import {
  Plus,
  Loader2,
  Users,
  Trash2,
  X,
  Shield,
  ChevronDown,
  Mail,
  Crown,
} from "lucide-react";

const ROLE_CONFIG: Record<string, { label: string; variant: "success" | "warning" | "secondary" | "default"; icon: typeof Shield }> = {
  owner: { label: "Owner", variant: "warning", icon: Crown },
  admin: { label: "Admin", variant: "success", icon: Shield },
  member: { label: "Member", variant: "default", icon: Users },
  viewer: { label: "Viewer", variant: "secondary", icon: Users },
};

const ROLES = ["owner", "admin", "member", "viewer"] as const;

interface MembersTabProps {
  tenantSlug: string;
  accessToken?: string;
}

export default function MembersTab({ tenantSlug, accessToken }: MembersTabProps) {
  const { error: toastError, success: toastSuccess } = useToast();
  const [members, setMembers] = useState<TenantMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [showInvite, setShowInvite] = useState(false);
  const [inviting, setInviting] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null);
  const [changingRole, setChangingRole] = useState<string | null>(null);

  // Invite form
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<string>("member");
  const [inviteDisplayName, setInviteDisplayName] = useState("");

  const loadMembers = useCallback(async () => {
    try {
      const m = await api.members.list(tenantSlug, accessToken);
      setMembers(m);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [tenantSlug, accessToken]);

  useEffect(() => {
    loadMembers();
  }, [loadMembers]);

  async function inviteMember() {
    if (!inviteEmail.trim()) return;
    setInviting(true);
    try {
      const member = await api.members.add(
        tenantSlug,
        {
          email: inviteEmail.trim(),
          role: inviteRole,
          display_name: inviteDisplayName.trim() || undefined,
        },
        accessToken
      );
      setMembers((prev) => [...prev, member]);
      toastSuccess(`Invited ${member.email}`);
      setShowInvite(false);
      setInviteEmail("");
      setInviteDisplayName("");
      setInviteRole("member");
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Failed to invite member");
    } finally {
      setInviting(false);
    }
  }

  async function updateRole(userId: string, newRole: string) {
    setChangingRole(userId);
    try {
      const updated = await api.members.update(tenantSlug, userId, { role: newRole }, accessToken);
      setMembers((prev) => prev.map((m) => (m.user_id === userId ? updated : m)));
      toastSuccess(`Role updated to ${newRole}`);
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Failed to update role");
    } finally {
      setChangingRole(null);
    }
  }

  async function removeMember(member: TenantMember) {
    if (!confirm(`Remove ${member.email} from this project?`)) return;
    setRemoving(member.user_id);
    try {
      await api.members.remove(tenantSlug, member.user_id, accessToken);
      setMembers((prev) => prev.filter((m) => m.user_id !== member.user_id));
      toastSuccess(`${member.email} removed`);
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Failed to remove member");
    } finally {
      setRemoving(null);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-5 h-5 animate-spin text-gray-400 dark:text-zinc-600" />
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <p className="text-sm text-gray-500 dark:text-zinc-500">
          {members.length} member{members.length !== 1 ? "s" : ""}
        </p>
        <button
          onClick={() => setShowInvite(true)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium transition-colors"
        >
          <Plus className="w-3 h-3" />
          Invite Member
        </button>
      </div>

      {/* Invite modal */}
      {showInvite && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
          <div className="bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-800 rounded-xl w-full max-w-md mx-4 shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-zinc-800">
              <div className="flex items-center gap-2">
                <Mail className="w-4 h-4 text-blue-500" />
                <h2 className="text-sm font-semibold text-gray-900 dark:text-zinc-100">Invite Team Member</h2>
              </div>
              <button onClick={() => setShowInvite(false)} className="text-gray-400 dark:text-zinc-600 hover:text-gray-700 dark:hover:text-gray-700 dark:text-zinc-300 transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-5 space-y-4">
              <div>
                <label className="block text-xs font-medium text-gray-500 dark:text-zinc-400 mb-1.5">Email address</label>
                <input
                  type="email"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  placeholder="colleague@gemeente.nl"
                  className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-zinc-700 bg-gray-100 dark:bg-zinc-800 text-sm text-gray-900 dark:text-zinc-100 placeholder:text-gray-400 dark:placeholder:text-zinc-600 focus:outline-none focus:border-blue-600 focus:ring-1 focus:ring-blue-600/30"
                  autoFocus
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-500 dark:text-zinc-400 mb-1.5">Display name (optional)</label>
                <input
                  type="text"
                  value={inviteDisplayName}
                  onChange={(e) => setInviteDisplayName(e.target.value)}
                  placeholder="Jan de Vries"
                  className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-zinc-700 bg-gray-100 dark:bg-zinc-800 text-sm text-gray-900 dark:text-zinc-100 placeholder:text-gray-400 dark:placeholder:text-zinc-600 focus:outline-none focus:border-blue-600 focus:ring-1 focus:ring-blue-600/30"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-500 dark:text-zinc-400 mb-1.5">Role</label>
                <div className="grid grid-cols-2 gap-2">
                  {ROLES.map((role) => {
                    const cfg = ROLE_CONFIG[role];
                    const selected = inviteRole === role;
                    return (
                      <button
                        key={role}
                        onClick={() => setInviteRole(role)}
                        className={`px-3 py-2.5 rounded-lg border text-left transition-colors ${
                          selected
                            ? "border-blue-600 bg-blue-600/10 text-blue-400"
                            : "border-gray-200 dark:border-zinc-800 bg-gray-50 dark:bg-zinc-800/50 text-gray-500 dark:text-zinc-500 hover:border-gray-400 dark:hover:border-gray-300 dark:border-zinc-700"
                        }`}
                      >
                        <p className="text-xs font-medium">{cfg.label}</p>
                        <p className="text-xs mt-0.5 opacity-60">
                          {role === "owner" && "Full access + billing"}
                          {role === "admin" && "Manage apps & services"}
                          {role === "member" && "Deploy & configure"}
                          {role === "viewer" && "Read-only access"}
                        </p>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  onClick={() => setShowInvite(false)}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium text-gray-500 dark:text-zinc-500 hover:text-gray-900 dark:hover:text-gray-800 dark:text-zinc-200 hover:bg-gray-100 dark:hover:bg-gray-100 dark:bg-zinc-800 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={inviteMember}
                  disabled={!inviteEmail.trim() || inviting}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {inviting && <Loader2 className="w-3 h-3 animate-spin" />}
                  Send Invite
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Member list */}
      {members.length === 0 ? (
        <div className="text-center py-16 border border-dashed border-gray-200 dark:border-zinc-800 rounded-xl">
          <Users className="w-8 h-8 mx-auto mb-2 text-gray-400 dark:text-zinc-700" />
          <p className="text-sm text-gray-500 dark:text-zinc-500">No team members yet.</p>
          <p className="text-xs text-gray-400 dark:text-zinc-600 mt-1">Invite your first team member to collaborate.</p>
        </div>
      ) : (
        <div className="bg-white dark:bg-zinc-900/50 border border-gray-200 dark:border-zinc-800 rounded-xl shadow-sm overflow-hidden">
          {members.map((member, idx) => {
            const cfg = ROLE_CONFIG[member.role] ?? ROLE_CONFIG.member;
            const initial = (member.display_name || member.email)[0].toUpperCase();

            return (
              <div
                key={member.id}
                className={`flex items-center gap-4 px-4 py-3.5 hover:bg-gray-100 dark:hover:bg-zinc-800/30 transition-colors ${
                  idx < members.length - 1 ? "border-b border-gray-200 dark:border-zinc-800/50" : ""
                }`}
              >
                {/* Avatar */}
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-600 to-violet-600 flex items-center justify-center shrink-0">
                  <span className="text-xs font-bold text-white">{initial}</span>
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-gray-800 dark:text-zinc-200 truncate">
                      {member.display_name || member.email.split("@")[0]}
                    </p>
                    {member.role === "owner" && <Crown className="w-3 h-3 text-amber-500 shrink-0" />}
                  </div>
                  <p className="text-xs text-gray-400 dark:text-zinc-600 truncate">{member.email}</p>
                </div>

                {/* Role selector */}
                <div className="relative">
                  {changingRole === member.user_id ? (
                    <Loader2 className="w-4 h-4 animate-spin text-gray-400 dark:text-zinc-600" />
                  ) : (
                    <div className="relative">
                      <select
                        value={member.role}
                        onChange={(e) => updateRole(member.user_id, e.target.value)}
                        className="appearance-none bg-gray-100 dark:bg-zinc-800 border border-gray-300 dark:border-zinc-700 rounded-lg px-3 py-1.5 pr-7 text-xs font-medium text-gray-700 dark:text-zinc-300 cursor-pointer hover:border-zinc-600 focus:outline-none focus:border-blue-600 transition-colors"
                      >
                        {ROLES.map((r) => (
                          <option key={r} value={r}>
                            {ROLE_CONFIG[r].label}
                          </option>
                        ))}
                      </select>
                      <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-gray-400 dark:text-zinc-600 pointer-events-none" />
                    </div>
                  )}
                </div>

                {/* Remove button */}
                <button
                  onClick={() => removeMember(member)}
                  disabled={removing === member.user_id}
                  className="text-gray-400 dark:text-zinc-700 hover:text-red-400 transition-colors disabled:opacity-50 shrink-0"
                  title="Remove member"
                >
                  {removing === member.user_id ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Trash2 className="w-3.5 h-3.5" />
                  )}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
